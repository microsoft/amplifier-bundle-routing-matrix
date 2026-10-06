"""Public checks; unchanged bytes are required by the assessor."""

import unittest

# These solver-side tests are run by stdlib unittest inside the isolated assessor,
# not collected as controller tests by the repository's pytest invocation.
__test__ = False


class PublicTests(unittest.TestCase):
    def setUp(self):
        from intervals import coalesce

        self.coalesce = coalesce

    def test_disjoint(self):
        self.assertEqual(self.coalesce([(2, 4), (8, 9)]), [(2, 4), (8, 9)])

    def test_invalid(self):
        for value in (None, "bad", [1], [(1,)], [(4, 2)], [(True, 2)]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.coalesce(value)


if __name__ == "__main__":
    unittest.main()
