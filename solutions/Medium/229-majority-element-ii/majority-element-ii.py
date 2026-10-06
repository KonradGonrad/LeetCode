from typing import List


# You are given an integer array nums of size n, find all elements that appear 
# more than ⌊ n/3 ⌋ times. You can return the result in any order.

class Solution:
    def majorityElement(self, nums: List[int]) -> List[int]:

        treshold = len(nums) // 3
        digits = set(nums) # set of digits that appear in the nums
        result = []

        if len(digits)!=len(nums):
            for digit in digits:
                if nums.count(digit)>treshold:
                    result.append(digit)
        
        else:
          if len(digits) < 3:
            return nums

        return result