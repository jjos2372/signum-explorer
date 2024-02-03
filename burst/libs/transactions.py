def get_message(attachment: bytes) -> str:
    header = attachment[:5]
    body = attachment[5:]
    message_len = 2**8 * header[2] + header[1]
    return body[:message_len].decode()


def get_message_sub(attachment: bytes) -> str:
    header = attachment[:10]
    body = attachment[10:]
    message_len = 2**8 * header[2] + header[1]
    return body[:message_len].decode()


def get_message_token(attachment: bytes) -> str:
    header = attachment[:22]
    body = attachment[22:]
    message_len = 2**8 * header[2] + header[1]
    return body[:message_len].decode()
