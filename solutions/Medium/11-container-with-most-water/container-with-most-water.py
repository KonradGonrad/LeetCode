from typing import List

class Solution:
    def maxArea(self, heights: List[int]) -> int:
        max_area = 0
        leftBar = 0
        rightBar = len(heights) - 1
        
        while leftBar < rightBar:
            h_left, h_right = heights[leftBar], heights[rightBar]

            if h_left < h_right:
              area = h_left * (rightBar - leftBar)

              if area > max_area:
                max_area = area

              while leftBar < rightBar and heights[leftBar] <= h_left:
                leftBar += 1

            else:

              area = h_right * (rightBar - leftBar)

              if area > max_area:
                    max_area = area

              while rightBar > leftBar and heights[rightBar] <= h_right:
                rightBar -= 1

        return max_area
          

