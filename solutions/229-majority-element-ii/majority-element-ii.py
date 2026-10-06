from typing import List


# You are given an integer array nums of size n, find all elements that appear 
# more than ⌊ n/3 ⌋ times. You can return the result in any order.

class Solution:
    def majorityElement(self, nums: List[int]) -> List[int]:
        treshold = len(nums) // 3

        digits = list(set(nums))
        counter = [0 for digit in digits]

        for i in range(len(nums)):
          counter[digits.index(nums[i])] += 1

        return [digits[i] for i in range(len(digits)) if counter[i] > treshold]