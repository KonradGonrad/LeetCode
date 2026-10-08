class MyQueue:

    def __init__(self):
        self.s1 = []
        self.s2 = []

    def push(self, x: int) -> None:
        self.s1.append(x)

    def move(self):
      if not self.s2:
            while self.s1:
                self.s2.append(self.s1.pop())

    def pop(self) -> int:
        self.move()
        return self.s2.pop()

    def peek(self) -> int:
        self.move()
        return self.s2[-1]

    def empty(self) -> bool:
        return not self.s1 and not self.s2 
