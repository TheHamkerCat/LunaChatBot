import unittest

from luna.group_log import MAX_TEXT_CHARS, OLDER_MESSAGE, GroupLogs


class GroupLogsTest(unittest.TestCase):
    def test_context_oldest_first_without_the_answered_message(self):
        logs = GroupLogs()
        logs.add(1, 10, "Priya", "match at 9?", 100)
        logs.add(1, 11, "Ravi", "luna you in?", 160, replied_id=10)
        self.assertEqual(logs.context(1, without_id=11), [
            {"name": "Priya", "text": "match at 9?", "time": 100, "reply_to": "", "is_luna": False},
        ])
        self.assertEqual(logs.context(1)[1]["reply_to"], "Priya")
        self.assertEqual(logs.context(2), [])

    def test_replies_to_luna_and_to_older_messages(self):
        logs = GroupLogs()
        logs.add(1, 10, "Ravi", "luna hi", 100)
        logs.add(1, 11, "Luna", "heyy", 101, replied_id=10, is_luna=True)
        logs.add(1, 12, "Ravi", "how are you", 102, replied_id=11)
        logs.add(1, 13, "Ravi", "remember this?", 103, replied_id=3)
        self.assertEqual([m["reply_to"] for m in logs.context(1)], ["", "Ravi", "Luna", OLDER_MESSAGE])
        self.assertTrue(logs.is_luna_message(1, 11))
        self.assertFalse(logs.is_luna_message(1, 10))
        self.assertIsNone(logs.is_luna_message(1, 3))
        self.assertIsNone(logs.is_luna_message(2, 11))

    def test_limits(self):
        logs = GroupLogs(max_messages=3, max_groups=2)
        for message_id in range(5):
            logs.add(1, message_id, "a", str(message_id), message_id)
        self.assertEqual([m["text"] for m in logs.context(1)], ["2", "3", "4"])
        logs.add(2, 1, "b", "x", 1)
        logs.add(1, 9, "a", "group 1 is active again", 9)
        logs.add(3, 1, "c", "x", 1)  # group 2 was least recently active
        self.assertEqual(logs.context(2), [])
        self.assertEqual(len(logs.context(1)), 3)

    def test_long_texts_and_names_are_cut(self):
        logs = GroupLogs()
        logs.add(1, 1, "N" * 100, "t" * 5000, 1)
        logs.add(1, 2, "", "hi", 2)
        first, second = logs.context(1)
        self.assertEqual(len(first["text"]), MAX_TEXT_CHARS)
        self.assertTrue(first["text"].endswith("…"))
        self.assertEqual(len(first["name"]), 64)
        self.assertEqual(second["name"], "someone")


if __name__ == "__main__":
    unittest.main()
