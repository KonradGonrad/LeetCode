class Solution:
    def productExceptSelf(self, nums: list[int]) -> list[int]:
        n = len(nums)
        
        left = [1] * n
        right = [1] * n
        output = [1] * n

        for i in range(1, len(nums)):

          left[i] = left[i-1] * nums[i - 1]
          right[n - i - 1] = right[n-i] * nums[n-i]

        for i in range(n):
          output[i] = left[i] * right[i]

        return output