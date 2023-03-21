import os
import shutil
import sqlite3
import hashlib

DATABASE_NAME = "cache_datagetter.db"
CACHE_DIR = "cache_dir"


def setup_database():
    con = sqlite3.connect(DATABASE_NAME)
    cur = con.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS cache
        (original_file_name TEXT NOT NULL UNIQUE,
         hash TEXT NOT NULL UNIQUE,
         json_file TEXT NOT NULL UNIQUE);"""
    )
    con.commit()
    con.close()


def setup_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def hash_file(original_file_path):
    file_hash = hashlib.sha1()

    with open(original_file_path, "rb") as fp:
        while True:
            data = fp.read(6000)
            if not data:
                break

            file_hash.update(data)

    return file_hash.hexdigest()


def get_file(file_hash_str):
    con = sqlite3.connect(DATABASE_NAME)
    cur = con.cursor()
    cur.execute("SELECT json_file FROM cache WHERE hash = ?", (file_hash_str,))
    row = cur.fetchone()
    con.close()

    # We haven't already converted the file
    if not row:
        return False

    # We have converted the file before so copy from the CACHE_DIR
    return os.path.join(CACHE_DIR, row[0])


def update_cache(json_file_name, file_hash_str, file_identifier, file_type):
    """
    Updates the cache database and copies the data into the cache dir
    json_file_name: Output desination for the file
    """
    con = sqlite3.connect(DATABASE_NAME)
    cur = con.cursor()

    cur.execute(
        """
    INSERT INTO cache (original_file_name, hash, json_file)
    VALUES (?, ?, ?)
    ON CONFLICT(original_file_name) DO UPDATE SET hash=?
    WHERE original_file_name=?
    """,
        (
            file_identifier + "." + file_type,
            file_hash_str,
            file_identifier + ".json",
            file_hash_str,
            file_identifier + "." + file_type,
        ),
    )

    con.commit()

    shutil.copy(json_file_name, CACHE_DIR)
