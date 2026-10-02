from typing import List

class Solution:
    def longestCommonPrefix(self, strs: List[str]) -> str:
        if not strs:
            return ""
        
        
        prefix = ''
        
        minString = strs.index(
            min(strs, key=len)
        )

        for i in range(len(strs[minString])):
          chr = strs[minString][i]
          if all(a[i] == chr for a in strs):
            prefix += chr
          else:
            break
        return prefix

