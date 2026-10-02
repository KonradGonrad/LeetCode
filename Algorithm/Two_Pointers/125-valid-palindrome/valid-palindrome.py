class Solution:
    def isPalindrome(self, s: str) -> bool:
        # isalnum only joins the letters and digits, ommiting at the same time different things like spaces and special characters.
        word = "".join(word for word in s if word.isalnum()).lower()

        return word == word[::-1]