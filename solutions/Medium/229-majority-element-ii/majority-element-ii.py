from typing import List
from collections import Counter

# You are given an integer array nums of size n, find all elements that appear 
# more than ⌊ n/3 ⌋ times. You can return the result in any order.

class Solution:
    def majorityElement(self, nums: List[int]) -> List[int]:
        treshold = len(nums) // 3

        counter = Counter(nums)

        return [digit for digit in list(counter.keys()) if counter[digit] > treshold]