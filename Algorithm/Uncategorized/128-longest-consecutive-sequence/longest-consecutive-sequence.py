class Solution:
    def longestConsecutive(self, nums: List[int]) -> int:

      # set of nums that is consisted of the digits without the duplicates, so we can omit the num1 == num2: continue
      num_set = set(nums)
      max_cnt = 0

      for num in num_set:
        # if the starting digit 
        if (num - 1) not in num_set:
          # current stats for digit and count 
          current_num = num
          current_cnt = 1

          # for each digit we search for continous sequence
          while (
              current_num +1 # while there is an digit that is greater by 1 than the current we can add both count and the digit that we already find out 
          ) in num_set:
            current_num += 1
            current_cnt += 1

          # where we cannot find any other greater digit we just simply assign our count if its greater that the current max with current count from while loop
          max_cnt = max(max_cnt, current_cnt)

        # After all nums in num_set we return max_count
      return max_cnt
