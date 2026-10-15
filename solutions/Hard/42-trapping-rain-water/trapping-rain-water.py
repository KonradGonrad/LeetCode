from typing import List

# Cases
# [3, 1, 2]
# [1, 1, 1]
# [2, 1, 3]
# [2, 1, 2]

class Solution:
    def trap(self, height: List[int]) -> int:
      n = len(height)
      # in these cases we cannot obtain the water trap, we need at least 3 points to enclose the water from both left and right side
      if n in (0, 1, 2):
        return 0

      water: int = 0 # amount of water trapped
      left: int = 0 
      right: int = n-1

      maxLeft, maxRight = height[left], height[right]

      while left < right:

        if height[left] < height[right]:
          if height[left] > maxLeft:
            maxLeft = height[left]
          else:
            water += maxLeft - height[left]
            left += 1
        else:
          if height[right] > maxRight:
            maxRight = height[right]
          else:
            water += maxRight - height[right]
            right -= 1

      return water
          
      
