import posixpath

def safe_join(root, user_path):  # bare startswith: /srv/app-evil passes for /srv/app
    joined = posixpath.normpath(posixpath.join(root, user_path))
    return joined if joined.startswith(posixpath.normpath(root)) else None
