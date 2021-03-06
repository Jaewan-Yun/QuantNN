class Unit(object):
    def __init__(self, id: int, name: str):
        self._id: int = id
        self._name: str = name

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name
