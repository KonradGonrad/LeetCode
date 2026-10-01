class Solution:
    def plusOne(self, digits: List[int]) -> List[int]:

        return [int(digit) for digit in str(sum([digit * 10**n for n, digit in enumerate(digits[::-1])]) + 1)]