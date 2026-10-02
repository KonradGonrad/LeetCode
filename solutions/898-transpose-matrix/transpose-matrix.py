from typing import List

class Solution:
    def transpose(self, matrix: List[List[int]]) -> List[List[int]]:
        rows = len(matrix)
        cols = len(matrix[0])

        result = [
            [0 for _ in range(rows)] for _ in range(cols)
        ]

        for i in range(rows):
          for j in range(cols):
            result[j][i] = matrix[i][j]

        return result
