from collections import Counter

class Solution:
    def groupAnagrams(self, strs: List[str]) -> List[List[str]]:
        output = {
            # key : [] -> key = str(sorted(word)) : [word1, word2, ...]
        }

        for word in strs:
            sorted_word = "".join(sorted(word))
            # print(sorted_word)

            # print(sorted_word in output)
            if sorted_word in output:
                output[sorted_word].append(word)
            else:
                output[sorted_word] = [word]

        return list(output.values())