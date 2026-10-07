from typing import List

# Input: nums = [2,-1,1,2], k = 2

# Output: 4
# [2], [2,-1,1], [-1,1,2], [2]

class Solution:
    def subarraySum(self, nums: List[int], k: int) -> int:
        currentSum: int = 0
        output: int = 0

        # for checking sums that appeared and counting them
        sums = {0: 1}

        
        for i in range(len(nums)):
            currentSum += nums[i]

            if currentSum - k in sums:
                output += sums[currentSum - k]

            if currentSum in sums:
                sums[currentSum] += 1
            else:
                sums[currentSum] = 1

        return output