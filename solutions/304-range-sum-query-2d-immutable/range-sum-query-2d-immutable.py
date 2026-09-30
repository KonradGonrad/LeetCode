class NumMatrix:

    def __init__(self, matrix: List[List[int]]):

      #  dimms of input matrix 
      m = len(matrix)    # number of rows
      n = len(matrix[0]) # number of cols

      # submatrix
      self.matrix = [ 
          [
              0 for _ in range(n +1)
          ]     for _ in range(m + 1) 
      ]

      

      # Calculating the continous sum of the digits in the cols and rows
      for row in range(m):
        for col in range(n):
          self.matrix[row+1][col+1] = matrix[row][col]

          # cols summing
          if col > 0:
            self.matrix[row +1][col +1] += self.matrix[row +1][col]

          # rows summing
          if row > 0:
            self.matrix[row + 1][col + 1] += self.matrix[row][col +1]

          # correction for overlapping
          if row > 0 and col > 0:
            self.matrix[row + 1][col + 1] -= self.matrix[row][col]
        

    def sumRegion(self, row1: int, col1: int, row2: int, col2: int) -> int:
      return self.matrix[row2 + 1][col2 + 1] - self.matrix[row1][col2 + 1] -self.matrix[row2 + 1][col1] + self.matrix[row1][col1]


# Your NumMatrix object will be instantiated and called as such:
# obj = NumMatrix(matrix)
# param_1 = obj.sumRegion(row1,col1,row2,col2)