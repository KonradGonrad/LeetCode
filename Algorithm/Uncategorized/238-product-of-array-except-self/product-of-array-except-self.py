import math

class Solution:
    def productExceptSelf(self, nums: list[int]) -> list[int]:
        n = len(nums)
        
        left = 1
        right = 1
        output = [1] * n

        for i in range(1, len(nums)):

          left *= nums[i - 1]
          output[i] *= left 

          right *= nums[n - i]
          output[n - i - 1] *= right
          

        return output
