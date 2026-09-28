class Solution:
    def longestConsecutive(self, nums: List[int]) -> int:
        n = len(nums)

        if n == 0:
          return 0

        nums = sorted(nums)
        max_cnt = 1
        cnt = 1

        for i in range(1, n):
          if nums[i] == nums[i - 1]:
            continue
          elif nums[i] == nums[i - 1] + 1:
            cnt += 1
            if cnt > max_cnt:
              max_cnt = cnt
          else:
            cnt = 1



        return max_cnt
