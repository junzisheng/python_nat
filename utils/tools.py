import uuid
import base64


def uid_base64():
    return base64.b64encode(str(uuid.uuid4()).encode()).decode()
