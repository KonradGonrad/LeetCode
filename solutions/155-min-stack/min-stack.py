class MinStack:

    def __init__(self):
        self.stack = [
            # (value, min)
        ]
        self.minStack = [

        ]

    def push(self, value: int) -> None:
        self.stack.append(value)

        if not self.minStack or value <= self.minStack[-1]:
            self.minStack.append(value)

        else:
            self.minStack.append(self.minStack[-1])

    def pop(self) -> None:
        # it do the pop inplace so its already popped out
        self.stack.pop(-1)
        self.minStack.pop(-1)

    def top(self) -> int:
        return self.stack[-1]

    def getMin(self) -> int:
        return self.minStack[-1]
        
# Your MinStack object will be instantiated and called as such:
# obj = MinStack()
# obj.push(value)
# obj.pop()
# param_3 = obj.top()
# param_4 = obj.getMin()