from collections import Counter

class Solution:
    def groupAnagrams(self, strs: List[str]) -> List[List[str]]:
        # Output: the solution of the problem.
        # the list of lists of anagrams [[x, y], [z], [a, b, c]]
        output = {}

        for word in strs:
            # count the letters in the word: "cat" -> Counter({'c': 1, 'a': 1, 't': 1})
            # To check if the words are equal
            counter = Counter(word)
            # print("Counter: ", counter)

            # key with frozenset to prevent duplicates and omit the order for the key, so the anagrams wont be placed in the different buckets, lists in the output list
            key = frozenset(counter.items())
            # print("key: ", key)
            # print()
            # adding the default empty list for the corresponding key and then appending to the empty list the word itself
            output.setdefault(key, []).append(word)

        # return the list of values, only the lists of words without the keys
        return list(output.values())
