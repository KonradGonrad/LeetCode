# n x n matrix -> 2x2, 3x3, ...
from typing import List

class Solution:
    def rotate(self, matrix: List[List[int]]) -> None:
      self.n = len(matrix)

      self.transpose(matrix)
      
      for i in range(self.n):
        for j in range(self.n // 2):
          matrix[i][j], matrix[i][self.n - 1 - j] = matrix[i][self.n - 1 - j], matrix[i][j]

    def transpose(self, matrix: List[List[int]]) -> None:
      for i in range(self.n):
        for j in range(i+1, self.n):
          
          matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]


        