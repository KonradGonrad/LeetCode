class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        # O(1)
        seen = {
            # number : idx
        }

        # O(n)
        # for each number in nums, i get its index and the number and i search for the needed number that is missing to get the target
        #  num[i] + num[j] = target
        #  num[j] is not known so its the searched one
        #  num[i] + searched = target -> searched = num[i] - target
        for idx, num in enumerate(nums):
          searched = target - num # digit i need to find the target, so i check if i have seen one in the list 

          # print(seen)
          # print(searched in seen)

          #  there I check if i have seen one, if so i return the indexes
          # O(1)
          if searched in seen:
            # print(seen[searched])
            # O(n) + O(1) + O(1) => O(n)
            return [seen[searched], idx]

          # if i havent seen any i just add the number and the index to the set
          # O(1)
          seen[num] = idx
                
