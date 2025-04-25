import os, sys; sys.path.insert(0, os.path.abspath(".")); import base64; print("Testing base64 decoding of g1..."); print(base64.urlsafe_b64decode("g1"))
