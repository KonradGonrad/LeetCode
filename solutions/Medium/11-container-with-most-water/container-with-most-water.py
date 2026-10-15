from typing import List

class Solution:
    def maxArea(self, heights: List[int]) -> int:
        max_area = 0
        leftBar = 0
        rightBar = len(heights) - 1
        
        while leftBar < rightBar:
            area = min(heights[leftBar], heights[rightBar]) * (rightBar - leftBar)
            max_area = max(max_area, area)

            if heights[leftBar] < heights[rightBar]:
                leftBar += 1
            else:
                rightBar -= 1
        
        return max_area
          

