from typing import List

# You are given an unsorted integer array nums. Return the smallest positive 
# integer that is not present in nums.

# Input: nums = [1,2,4]
# Output: 3

# Input: nums = [-2,-1,0]
# Output: 1

class Solution:
    def firstMissingPositive(self, nums: List[int]) -> int:
        nums_set = set(nums) # Set of nums without duplicates

        # For i: digit in range of 1 to len(nums) + 2 we are searching the digit that is positive (>= 1) and is in range of the digits of the nums or above it, because the seached digit can be greater than the greatest digit in existing nums, for example in [1, 2, 3] we search for 4, thats the corner case as well as when the list is empty so we iterate till the 1, which is the result
        for i in range(1, len(nums) + 2):
            # if i isn't in the set then it is the searched digit
          if i not in nums_set:
            return i