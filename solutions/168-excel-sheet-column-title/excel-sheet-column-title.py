class Solution:
    def convertToTitle(self, columnNumber: int) -> str:
        result = ""
        while(columnNumber>0):
            columnNumber-=1
            value = (columnNumber)%26
            result+=chr(65+value)
            columnNumber //= 26
        return result[::-1]




