import posixpath

def safe_join(root, user_path):
    root_norm = posixpath.normpath(root)
    joined = posixpath.normpath(posixpath.join(root_norm, user_path))
    if joined == root_norm or joined.startswith(root_norm + "/"):
        return joined
    return None
