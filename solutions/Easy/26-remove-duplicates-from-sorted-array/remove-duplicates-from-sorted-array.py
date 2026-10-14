from typing import List

class Solution:
    def removeDuplicates(self, nums: List[int]) -> int:
        n = len(nums)
        if n in (0, 1):
            return n

        left: int = 0 # starting index that will be our unique numbers index
        right: int = 0 #index of the number that we will compare to

        while right < n:
            if nums[left] != nums[right]:
                left += 1
                nums[left] = nums[right]
            right += 1
          
        # nums[:left + 1] # list of unique elements
        # left + 1 # number of unique elements
        return left + 1
            