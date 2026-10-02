from typing import List

class Solution:
    def removeElement(self, nums: List[int], val: int) -> int:
        temp = []

        for element in nums:
            if element != val:
                temp.append(element)

        for i in range(len(temp)):
            nums[i] = temp[i]
      
        return len(temp)