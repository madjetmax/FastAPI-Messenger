import re
from fastapi import HTTPException
from fastapi import status

from src.config import settings

usernames_pattern = re.compile(
    rf'^(?=.*[a-z])[A-Za-z\d_.-]{{{settings.auth.username_min_len},{settings.auth.username_max_len}}}$'
)
def validate_username(username: str):
    # search pattern in usenrame
    if not usernames_pattern.fullmatch(username.strip()):
        raise ValueError(
            "Username is invalid"
        )

def validate_first_name(name: str):
    clear_name = name.lower().strip()
    # check clear len
    if len(clear_name) < settings.auth.first_name_min_len or len(clear_name) > settings.auth.first_name_max_len:
        raise ValueError(
            "First name is invalid"
        )
    
def validate_last_name(name: str):
    # check clear len
    if len(name.lower().strip()) > settings.auth.last_name_max_len:
        raise ValueError(
            "Last name is invalid"
        )

passwords_pattern = re.compile(
    rf"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[~`!@#$%^&*()_\-+=\[\]{{}}|\\:;\"'<>,.?/])[A-Za-z\d~`!@#$%^&*()_\-+=\[\]{{}}|\\:;\"'<>,.?/]{{{settings.auth.password_min_len},{settings.auth.password_max_len}}}$" 
)
def validate_password(password: str):
    # search pattern in password
    if not passwords_pattern.fullmatch(password):
    # if not re.search(passwords_pattern, password):
        # not strong
        raise ValueError(
            "Password is not strong"
        )
    
    return True
