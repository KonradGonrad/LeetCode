from typing import List

class Solution:
    def threeSum(self, nums: List[int]) -> List[List[int]]:
        """
          Algorithm to search for each digit ( List[idx] ) two other digits x1, x2 that combined gives us 0. So x1 + x2 + List[idx] = 0 -> x1 + x2 = -List[idx]
        """
        
        n = len(nums) # number of elements - total
        nums.sort() # sorting for better iteration

        sums = []

        # in the range of the len(nums) - 2, because we then just search 2 left digits, so that whats left are our x1 and x2
        for idx in range(n - 2):
          # Because we sorted nums we got greater digits on the right hand side of our nums[idx], so we cannot get 0 from all positive numbers
          if nums[idx] > 0:
            break

          if idx > 0 and nums[idx] == nums[idx - 1]:
            continue

          # searched value to achieve 0 from left 2 digits in the list
          searchedValue =  - nums[idx]
          
          # searched values
          x1: int = idx + 1
          x2: int = n-1

          # we are checking from the left to the right, on the right hand side of our nums[idx]
          while x1 < x2:
            currentSum = nums[x1] + nums[x2]

            # if we got a match we add our combination and both increments x1 and decrements x2
            if currentSum == searchedValue:
              sums.append([nums[idx], nums[x1], nums[x2]])
            
              x1 += 1
              x2 -= 1

              # omit duplicates, when there is situation when we got the same numbers from the ascending side
              while x1 < x2 and nums[x1] == nums[x1 - 1]:
                      x1 += 1

            # if our current sum is lower than searched value we need to add index x1 because it is sorted in ascending order, in the other case we need to decrease the index of x2, so search for the lower number in the equation
            elif currentSum < searchedValue:
              x1 += 1
            else:
              x2 -= 1

        return sums
