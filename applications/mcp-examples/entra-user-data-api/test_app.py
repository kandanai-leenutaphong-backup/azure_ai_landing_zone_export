import asyncio
import unittest

from fastapi import HTTPException

from app import get_my_profile, list_my_orders


class UserDataIsolationTests(unittest.TestCase):
    def test_users_receive_different_records(self) -> None:
        async def run() -> None:
            first_profile = await get_my_profile("user-a", "User A", "a@example.com")
            second_profile = await get_my_profile("user-b", "User B", "b@example.com")
            first_orders = await list_my_orders("user-a", "User A", "a@example.com")
            second_orders = await list_my_orders("user-b", "User B", "b@example.com")

            self.assertNotEqual(first_profile["demo_employee_number"], second_profile["demo_employee_number"])
            self.assertNotEqual(first_orders["orders"], second_orders["orders"])

        asyncio.run(run())

    def test_missing_identity_is_rejected(self) -> None:
        async def run() -> None:
            with self.assertRaises(HTTPException) as context:
                await get_my_profile(None, None, None)
            self.assertEqual(context.exception.status_code, 401)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
