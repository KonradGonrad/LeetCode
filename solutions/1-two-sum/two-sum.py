class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        for i in range(len(nums) - 1): # in the range we exclude the searched digit 
            # Because the lists are already sorted, we can assume that the left one digit is the pivot that is searching the corresponding digit to match target with matching the condition to find the smallest index first, the others we don't consider
            pivot = nums[i] # pivot chosen in the loop 

            for j in range(i + 1, len(nums), 1): # i+1 because we omit the pivot to not duplicate searched digits
                # print(pivot, nums[j])
                if pivot + nums[j] == target:
                    return [i, j]

                
