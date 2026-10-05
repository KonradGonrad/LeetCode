class Solution:
    def calPoints(self, operations: List[str]) -> int:
      temp, total = [], 0
      

      for i in range(len(operations)):
        
        if operations[i] == '+':
            temp.append(
                int(temp[-2]) + int(temp[-1])
            )
            total += temp[-1]

        elif operations[i] == 'D':
            temp.append(
                int(temp[-1]) * 2
            )
            total += temp[-1]

        elif operations[i] == 'C':
            total -= temp.pop()

        else:
            temp.append(
                int(operations[i])
            )
            total += temp[-1]


      

      return total
    