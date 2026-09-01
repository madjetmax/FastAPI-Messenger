

# * user, auth
class DBUserAlreadyExistsError(Exception):
    pass

class DBUserDoesNotExists(Exception):
    pass

class DBUserDataUpdateConflict(Exception):
    def __init__(self, *args, conflict_columns: list[str]):
        super().__init__(*args)

        self.conflict_columns: list[str] = conflict_columns

class DBUserSessionsLimit(Exception):
    pass


# * chattings
class DBPrivateChatAlreadyExistsError(Exception):
    pass

class DBPrivateChatDoesnotExists(Exception):
    pass