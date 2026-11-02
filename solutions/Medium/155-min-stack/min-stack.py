class MinStack:

    def __init__(self):
        self.stack = [
            # (value, min)
        ]

    def _getMin(self, value) -> int:
        if len(self.stack) == 0:
            return value

        else:
            curr = self.stack[-1][1]
            return curr if curr < value else value

    def push(self, value: int) -> None:
        self.stack.append((value, self._getMin(value)))

    def pop(self) -> None:
        self.stack.pop(-1)

    def top(self) -> int:
        return self.stack[-1][0]

    def getMin(self) -> int:
        return self.stack[-1][1]
        


# Your MinStack object will be instantiated and called as such:
# obj = MinStack()
# obj.push(value)
# obj.pop()
# param_3 = obj.top()
# param_4 = obj.getMin()