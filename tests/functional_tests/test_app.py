from typing import Awaitable, Callable, List

import pytest
from harlequin import Harlequin
from harlequin.components import ErrorModal


@pytest.mark.asyncio
async def test_select_1(
    app_all_adapters: Harlequin, app_snapshot: Callable[..., Awaitable[bool]]
) -> None:
    app = app_all_adapters
    async with app.run_test() as pilot:
        assert app.title == "Harlequin"
        assert app.focused.__class__.__name__ == "TextInput"

        q = "select 1 as foo"
        for key in q:
            await pilot.press(key)
        await pilot.press("ctrl+j")  # alias for ctrl+enter

        await pilot.pause()
        assert app.query_text == q
        assert app.cursors
        table = app.results_viewer.get_visible_table()
        assert table
        assert table.source_row_count == table.row_count == 1
        assert await app_snapshot(app, "select 1 as foo")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "select 1+1",
        "select 'a' as foo",
        "select null",
        "select null as foo",
        "",
        "select 1 where false",
    ],
)
async def test_queries_do_not_crash_all_adapters(
    app_all_adapters: Harlequin,
    query: str,
    app_snapshot: Callable[..., Awaitable[bool]],
) -> None:
    app = app_all_adapters
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.editor.text = query
        await pilot.press("ctrl+j")
        await pilot.pause()

        assert app.query_text == query
        if query:
            assert app.cursors
        assert await app_snapshot(app, query or "<empty query>")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "SELECT {'x': 1, 'y': 2, 'z': 3}",  # struct
        # also a struct:
        "SELECT {'yes': 'duck', 'maybe': 'goose', 'huh': NULL, 'no': 'heron'}",
        "SELECT {'key1': 'string', 'key2': 1, 'key3': 12.345}",  # struct
        """SELECT {'birds':
            {'yes': 'duck', 'maybe': 'goose', 'huh': NULL, 'no': 'heron'},
        'aliens':
            NULL} as bar""",  # struct
        "select {'a': 5} union all select {'a': 6}",  # struct
        "select map {'a': 5}",  # map
        "select map {'a': 5} union all select map {'b': 6}",  # map
        "SELECT map { 1: 42.001, 5: -32.1 }",  # map
        "SELECT map { ['a', 'b']: [1.1, 2.2], ['c', 'd']: [3.3, 4.4] }",  # map
        "SELECT [1, 2, 3]",  # list
        "SELECT ['duck', 'goose', NULL, 'heron'];",  # list
        "SELECT [['duck', 'goose', 'heron'], NULL, ['frog', 'toad'], []];",  # list
    ],
)
async def test_queries_do_not_crash(
    app: Harlequin, query: str, app_snapshot: Callable[..., Awaitable[bool]]
) -> None:
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.editor.text = query
        await pilot.press("ctrl+j")
        await pilot.pause()

        assert app.query_text == query
        if query:
            assert app.cursors
        assert await app_snapshot(app, query or "<empty query>")


@pytest.mark.asyncio
async def test_multiple_queries(
    app_all_adapters: Harlequin, app_snapshot: Callable[..., Awaitable[bool]]
) -> None:
    app = app_all_adapters
    snap_results: List[bool] = []
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        q = "select 1; select 2"
        app.editor.text = q
        await pilot.press("ctrl+j")

        # should only run one query
        await pilot.pause()
        assert app.query_text == "select 1;"
        table = app.results_viewer.get_visible_table()
        assert table
        assert table.row_count == table.source_row_count == 1
        assert "hide-tabs" in app.results_viewer.classes
        snap_results.append(await app_snapshot(app, "One query"))

        app.editor.focus()
        await pilot.press("ctrl+a")
        await pilot.press("ctrl+j")
        # should run both queries
        await pilot.pause()
        await pilot.wait_for_scheduled_animations()
        assert app.query_text == "select 1; select 2"
        assert app.results_viewer.tab_switcher.tab_count == 2
        assert "hide-tabs" not in app.results_viewer.classes
        snap_results.append(await app_snapshot(app, "Both queries"))
        assert app.results_viewer.tab_switcher.active == "tab-2"
        await pilot.press("k")
        await pilot.wait_for_scheduled_animations()
        assert app.results_viewer.tab_switcher.active == "tab-1"
        snap_results.append(await app_snapshot(app, "Both queries, tab 1"))
        await pilot.press("k")
        await pilot.wait_for_scheduled_animations()
        assert app.results_viewer.tab_switcher.active == "tab-2"
        snap_results.append(await app_snapshot(app, "Both queries, tab 2"))
        await pilot.press("j")
        assert app.results_viewer.tab_switcher.active == "tab-1"
        await pilot.press("j")
        assert app.results_viewer.tab_switcher.active == "tab-2"

        assert all(snap_results)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_query",
    [
        "select",  # errors when building cursor
        "select 0::struct(id int)",  # errors when fetching data
        "select; select 0::struct(id int)",  # multiple errors
        "select 1; select 0::struct(id int)",  # one error, mult queries
        "select 0::struct(id int); select 1",  # one error, mult queries, err first
        """
            CREATE TABLE tbl1(u UNION(num INT, str VARCHAR));
            INSERT INTO tbl1 values (1) , ('two') , (union_value(str := 'three'));
            SELECT u FROM tbl1;
        """,  # arrow doesn't do union types.
    ],
)
async def test_query_errors(
    app_all_adapters: Harlequin,
    bad_query: str,
    app_snapshot: Callable[..., Awaitable[bool]],
) -> None:
    app = app_all_adapters
    snap_results: List[bool] = []
    async with app.run_test(size=(120, 36)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.editor.text = bad_query

        await pilot.press("ctrl+a")
        await pilot.press("ctrl+j")
        assert len(app.screen_stack) == 2
        assert isinstance(app.screen, ErrorModal)
        snap_results.append(await app_snapshot(app, "Error visible"))

        await pilot.press("space")
        assert len(app.screen_stack) == 1

        # data table and query bar should be responsive
        assert "non-responsive" not in app.run_query_bar.classes
        assert "non-responsive" not in app.results_viewer.classes
        snap_results.append(await app_snapshot(app, "After dismissing error"))

        assert all(snap_results)
