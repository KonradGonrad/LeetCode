class MyHashSet:

    def __init__(self):
        self.hashset = []
        

    def add(self, key: int) -> None:
        if key not in self.hashset:
          self.hashset.append(key)

    def remove(self, key: int) -> None:
        if key in self.hashset:
          self.hashset.remove(key)

    def contains(self, key: int) -> bool:
        if key in self.hashset:
            return True
        return False