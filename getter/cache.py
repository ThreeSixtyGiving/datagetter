import os
import shutil
import apsw
import hashlib

DATABASE_NAME = "cache_datagetter.db"
CACHE_DIR = "cache_dir"

class DatagetterCacheError(Exception):
    pass


def setup_database():
    try:
        con = apsw.Connection(DATABASE_NAME)
        cur = con.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS cache
            (original_file_name TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL UNIQUE,
            json_file TEXT NOT NULL UNIQUE);"""
        )
        con.close()
    except Exception as e:
        raise DatagetterCacheError(e)


def setup_cache_dir():
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception as e:
        raise DatagetterCacheError(e)


def hash_file(original_file_path):
    try:
        file_hash = hashlib.sha1()

        with open(original_file_path, "rb") as fp:
            while True:
                data = fp.read(6000)
                if not data:
                    break

                file_hash.update(data)
    except Exception as e:
        raise DatagetterCacheError(e)

    return file_hash.hexdigest()


def get_file(file_hash_str):
    try:
        con = apsw.Connection(DATABASE_NAME)
        cur = con.cursor()
        cur.execute("SELECT json_file FROM cache WHERE hash = ?", (file_hash_str,))
        row = cur.fetchone()
        con.close()

        # We haven't already converted the file
        if not row:
            return False

        # We have converted the file before so copy from the CACHE_DIR
        return os.path.join(CACHE_DIR, row[0])
    except Exception as e:
        raise DatagetterCacheError(e)


def update_cache(json_file_name, file_hash_str, file_identifier, file_type):
    """
    Updates the cache database and copies the data into the cache dir
    json_file_name: Output desination for the file
    """
    # Todo clean up cache functionality for orphaned files or to reset the cache

    try:
        con = apsw.Connection(DATABASE_NAME)
        cur = con.cursor()

        cur.execute(
            """
        INSERT INTO cache (original_file_name, hash, json_file)
        VALUES (?, ?, ?)
        ON CONFLICT(original_file_name) DO UPDATE SET hash=?
        ON CONFLICT(json_file) DO UPDATE SET hash=?, original_file_name=?
        """,
            (
                file_identifier + "." + file_type,
                file_hash_str,
                file_identifier + ".json",
                file_hash_str,
                file_hash_str,
                file_identifier + "." + file_type,
            ),
        )

        shutil.copy(json_file_name, CACHE_DIR)
    except Exception as e:
        raise DatagetterCacheError(e)
