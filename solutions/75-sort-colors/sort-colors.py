from typing import List

class Solution:
    def sortColors(self, nums: List[int]) -> None:
        """
        Do not return anything, modify nums in-place instead.
        """
        # nums are only:
        # 0 - red   1 - white   2 - blue
        # order: red -> white -> blue

        # counting the values of colors
        count = [0 for i in range(3)]
        # [red, white, blue]

        # counting the colors
        for i in range(len(nums)):
          count[nums[i]] += 1

        # changing the nums list
        idx = 0
        for value in range(len(count)):
          # number of digits left for each color
          digits = count[value]
          # while we have some more digits left:
          while digits > 0:
            # we change the nums idx for value (RWB)
            nums[idx] = value
            # we add index and we decrease the left digits
            idx += 1
            digits -= 1