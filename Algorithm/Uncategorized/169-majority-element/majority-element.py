class Solution:
    def majorityElement(self, nums: List[int]) -> int:
        treshold = len(nums) / 2

        for num in set(nums):
          if nums.count(num) > treshold:
            return num