class Solution:
    def mergeAlternately(self, word1: str, word2: str) -> str:
      l, r = 0, 0
      chars = len(word1) + len(word2)
      output = []

      while l + r < chars:
        if l < len(word1):
          output.append( word1[l] )
          l += 1
        if r < len(word2):
          output.append( word2[r] )
          r += 1

      return "".join(output)