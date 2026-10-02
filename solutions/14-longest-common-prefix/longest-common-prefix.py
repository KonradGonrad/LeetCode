from typing import List

class Solution:
    def longestCommonPrefix(self, strs: List[str]) -> str:
        if not strs:
            return ""
        
        
        prefix = ''
        i = 0

        while i < len(strs[0]) and all(
            word.startswith(prefix + strs[0][i]) for word in strs
        ):
            prefix += strs[0][i]
            i += 1
        
        return prefix

