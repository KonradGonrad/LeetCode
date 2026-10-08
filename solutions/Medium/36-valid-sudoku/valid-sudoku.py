from typing import List

class Solution:
    def isValidSudoku(self, board: List[List[str]]) -> bool:
      # it's always 9x9, with 3 squares of size 3x3
      boardSize = len(board)

      # lists where I will put the actual digits in the rows and cols and then I will check if somedigit is in the set already to validate if the sudoku is valid
      rows = [
          set() for i in range(boardSize)
      ]
      cols = [
          set() for i in range(boardSize)
      ]
      boxes = [
          set() for i in range(boardSize)
      ]

      for rowItem in range(boardSize):
        for colItem in range(boardSize):
          if board[rowItem][colItem] == ".":
            continue
          else:
            # checking rows
            if board[rowItem][colItem] in rows[rowItem]:
              return False
            else:
              rows[rowItem].add(board[rowItem][colItem])

            # checking cols
            if board[rowItem][colItem] in cols[colItem]:
              return False
            else:
              cols[colItem].add(board[rowItem][colItem])

            # box index
            boxIndex = (rowItem // 3) * 3 + (colItem // 3)

            # checking boxes
            if board[rowItem][colItem] in boxes[boxIndex]:
              return False
            else:
              boxes[boxIndex].add(board[rowItem][colItem])
              
      return True