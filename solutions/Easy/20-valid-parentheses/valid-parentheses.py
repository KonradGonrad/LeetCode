class Solution:
    def isValid(self, s: str) -> bool:
        if len(s) % 2 != 0:
          return False

        last_seen = []

        bracket_dict = {
            ')' : '(',
            '}' : '{',
            ']' : '[',
        }

        for bracket in s:

          # opening bracket case
          if bracket in ['(', '{', '[']:
              last_seen.append(bracket)

          #  closing bracket case
          else:
            # if last_seen is empty then we cannot have the closing one
            if not last_seen:
              return False
            # if the closing bracket doesn't match the opening one, that's seen in the last_seen then false
            if bracket_dict[bracket] != last_seen[-1]:
              return False
            else:
              last_seen.pop()
        
        return True if not last_seen else False

