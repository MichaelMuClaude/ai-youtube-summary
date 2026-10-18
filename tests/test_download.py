"""Tests for ai_youtube_summary.download (ported from the former ai-youtube project)."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_youtube_summary.download import (
    _LIBRARY,
    _DIRS,
    HIT_THRESHOLD,
    is_url,
    build_search_prefix,
    yt_dlp_args,
    download,
    search,
    check,
    normalize,
    score,
    VALID_KINDS,
    _extract_downloaded_path,
    _video_codec_name,
    _check_downloaded_video_codec,
)
from ai_youtube_summary.errors import SummaryError


# ── is_url ───────────────────────────────────────

class TestIsUrl:
    @pytest.mark.parametrize("s, expected", [
        ("https://youtu.be/xxx", True),
        ("http://example.com", True),
        ("http://example.com/path?q=1", True),
        ("野狼disco", False),
        ("ytsearch1:something", False),
        ("", False),
    ])
    def test_is_url(self, s, expected):
        assert is_url(s) == expected


# ── build_search_prefix ─────────────────────────

class TestBuildSearchPrefix:
    @pytest.mark.parametrize("kind", ("song", "lofi", "video"))
    def test_keyword_wrapped_ytsearch1(self, kind):
        result = build_search_prefix(kind, "野狼disco")
        assert result == "ytsearch1:野狼disco"

    @pytest.mark.parametrize("url", (
        "https://youtu.be/abc123",
        "http://example.com/watch?v=xyz",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ))
    def test_url_passthrough(self, url):
        assert build_search_prefix("song", url) == url


# ── yt_dlp_args ─────────────────────────────────

class TestYtDlpArgs:
    @pytest.mark.parametrize("kind", ("song", "lofi", "video"))
    def test_common_base_flags(self, kind):
        args = yt_dlp_args(kind, "test_target")
        assert args[0] == "yt-dlp"
        assert "--no-playlist" in args
        assert "--no-warnings" in args
        assert "--progress" in args
        assert "-o" in args
        assert "--windows-filenames" in args

    @pytest.mark.parametrize("kind", ("song", "lofi"))
    def test_audio_flags(self, kind):
        args = yt_dlp_args(kind, "test_target")
        assert "-x" in args
        idx_af = args.index("--audio-format")
        assert args[idx_af + 1] == "mp3"
        idx_aq = args.index("--audio-quality")
        if kind == "song":
            assert args[idx_aq + 1] == "0"
        else:
            assert args[idx_aq + 1] == "5"
        assert "--embed-thumbnail" in args
        assert "--embed-metadata" in args
        assert "--add-metadata" in args
        p_idx = args.index("--print")
        assert args[p_idx + 1] == "after_move:filepath"

    def test_video_flags(self):
        args = yt_dlp_args("video", "https://youtu.be/xxx")
        assert "-f" in args
        f_idx = args.index("-f")
        assert (
            args[f_idx + 1] ==
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        )
        idx_mof = args.index("--merge-output-format")
        assert args[idx_mof + 1] == "mp4"
        assert "--write-auto-sub" in args
        sl_idx = args.index("--sub-lang")
        assert args[sl_idx + 1] == "en,zh"
        assert "--embed-subs" in args
        p_idx = args.index("--print")
        assert args[p_idx + 1] == "after_move:filepath"

    @pytest.mark.parametrize("kind", ("song", "lofi"))
    def test_output_dir(self, kind):
        expected_dirs = {"song": "Songs", "lofi": "Lofi"}
        args = yt_dlp_args(kind, "test_target")
        o_idx = args.index("-o")
        expected = os.path.join(_LIBRARY, expected_dirs[kind]) + "/"
        assert expected in args[o_idx + 1]

    def test_video_output_dir(self):
        args = yt_dlp_args("video", "test_target")
        o_idx = args.index("-o")
        expected = os.path.join(_LIBRARY, "Videos") + "/"
        assert expected in args[o_idx + 1]

    def test_target_is_last(self):
        for kind, target in [
            ("song", "ytsearch1:test"),
            ("video", "https://example.com/watch?v=123"),
        ]:
            args = yt_dlp_args(kind, target)
            assert args[-1] == target


# ── search() ─────────────────────────────────────

class TestSearch:
    def _make_result(self, stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=returncode, stdout=stdout, stderr=""
        )

    def test_search_prints_numbered_results(self, capsys):
        stdout = (
            "Eagles - Hotel California (Live 1977)\thttps://youtu.be/abc\t405\n"
            "Eagles - Hotel California (Official Audio)\thttps://youtu.be/def\t391"
        )
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(stdout=stdout)
            search("hotel california eagles")

        captured = capsys.readouterr()
        assert "[search]" in captured.out
        assert "1. Eagles - Hotel California (Live 1977)" in captured.out
        assert "https://youtu.be/abc" in captured.out
        assert "(6:45)" in captured.out
        assert "2. Eagles - Hotel California (Official Audio)" in captured.out
        assert "(6:31)" in captured.out
        assert "[ok] 想下载哪首" in captured.out

    def test_search_no_results(self, capsys):
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(stdout="")
            search("xyz unlikely query")

        captured = capsys.readouterr()
        assert "没有搜到" in captured.out

    def test_search_propagates_ytdlp_error(self):
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(stdout="", returncode=1)
            with pytest.raises(SystemExit) as exc_info:
                search("test query")
            assert exc_info.value.code == 1

    def test_search_handles_na_duration(self, capsys):
        stdout = "Live Stream\thttps://youtu.be/live\tNA"
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(stdout=stdout)
            search("live")

        captured = capsys.readouterr()
        assert "Live Stream" in captured.out
        assert "(--:--)" in captured.out

    def test_search_builds_ytsearch_prefix(self):
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_run.return_value = self._make_result(stdout="")
            search("test query", count=5)

        args = mock_run.call_args[0][0]
        assert args[0] == "yt-dlp"
        assert "--flat-playlist" in args
        assert "--no-warnings" in args
        assert args[-1] == "ytsearch5:test query"


# ── download() failure path ─────────────────────

class TestDownloadFailure:
    def test_download_raises_on_nonzero_exit(self):
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_result = subprocess.CompletedProcess(
                args=["yt-dlp"], returncode=42
            )
            mock_run.return_value = mock_result

            with pytest.raises(SummaryError):
                download("song", "test query")

    def test_download_succeeds(self):
        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            mock_result = subprocess.CompletedProcess(
                args=["yt-dlp"], returncode=0
            )
            mock_run.return_value = mock_result

            path = download("song", "test query")
            assert mock_run.called
            assert path == _DIRS["song"]

    def test_download_song_resolves_exact_path_from_ytdlp_output(self, tmp_path, monkeypatch):
        songs_dir = tmp_path / "Songs"
        songs_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setitem(_DIRS, "song", str(songs_dir))
        exact_path = songs_dir / "Some Song.mp3"

        def fake_run(args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=f"{exact_path}\n")

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", fake_run)
        path = download("song", "test query")
        assert path == str(exact_path)


# ── VALID_KINDS ──────────────────────────────────

class TestValidKinds:
    def test_valid_kinds_includes_search_and_check(self):
        assert VALID_KINDS == {"song", "lofi", "video", "search", "check"}


# ── normalize() / score() ────────────────────────

class TestNormalize:
    @pytest.mark.parametrize("raw, expected", [
        (
            "Eagles - Hotel California (Official Video) [HD]",
            "eagles hotel california",
        ),
        (
            "1. Blue Swede - Hooked on a Feeling",
            "blue swede hooked on a feeling",
        ),
        (
            "2. Raspberries - Go All The Way",
            "raspberries go all the way",
        ),
        (
            "21 Guns",
            "21 guns",
        ),
        (
            "50 Cent - Candy Shop (Official Music Video) ft. Olivia",
            "50 cent candy shop olivia",
        ),
        (
            "Around the World (La La La La La)",
            "around the world",
        ),
        (
            "Alan Walker - Faded",
            "alan walker faded",
        ),
        (
            "#周深 大鱼",
            "大鱼",
        ),
        (
            "A｜B／C",
            "a b c",
        ),
    ])
    def test_normalize_cases(self, raw, expected):
        assert normalize(raw) == expected


class TestScore:
    def test_exact_substring_returns_one(self):
        assert score("hotel california", "eagles hotel california official audio") == 1.0

    def test_token_containment(self):
        s = score("hotel california eagles", "eagles hotel california official audio")
        assert s == 0.9 * 3 / 5

    def test_21_guns_not_mistaken_for_sequence_prefix(self):
        assert score("21 guns", "21 guns") == 1.0
        assert score("21 guns", "21 guns live") == 1.0

    def test_non_duplicate_is_low(self):
        s = score(normalize("你的微笑"), normalize("your smile makes my heart happy [Lofi]"))
        assert s < HIT_THRESHOLD

    def test_design_doc_hotel_california(self):
        assert score(
            normalize("Hotel California"),
            normalize("Eagles - Hotel California (Live 1977) (Official Video) [HD]"),
        ) == 1.0

    def test_design_doc_around_the_world(self):
        s = score(
            normalize("Around the World La La La"),
            normalize("Around the World (La La La La La)"),
        )
        assert s >= HIT_THRESHOLD


# ── check() ──────────────────────────────────────

class TestCheck:
    def _patch_dirs(self, tmp_path, monkeypatch):
        for kind, label in [("song", "Songs"), ("lofi", "Lofi"), ("video", "Videos")]:
            monkeypatch.setitem(_DIRS, kind, str(tmp_path / label))
            (tmp_path / label).mkdir(parents=True, exist_ok=True)

    def _make_file(self, tmp_path, label: str, filename: str):
        directory = tmp_path / label
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_text("")
        return directory

    def test_hit_finds_local_duplicate(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Songs", "Eagles - Hotel California (Official Audio).mp3")

        check("Hotel California")
        captured = capsys.readouterr()
        assert "[check]" in captured.out
        assert "Eagles - Hotel California (Official Audio).mp3" in captured.out
        assert "[命中]" in captured.out

    def test_miss_when_no_duplicate(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Songs", "Oasis - Wonderwall (Official Video).mp3")

        check("Hotel California")
        captured = capsys.readouterr()
        assert "[check]" in captured.out
        assert "[未命中]" in captured.out

    def test_empty_library(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)

        check("anything")
        captured = capsys.readouterr()
        assert "媒体库为空" in captured.out

    def test_check_does_not_call_ytdlp(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Songs", "Alan Walker - Faded.mp3")

        with patch("ai_youtube_summary.download.subprocess.run") as mock_run:
            check("Faded")
            assert not mock_run.called

    def test_video_mp4_hit(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Videos", "Demo Video.mp4")

        check("Demo Video")
        captured = capsys.readouterr()
        assert "Demo Video.mp4" in captured.out
        assert "[Videos]" in captured.out
        assert "[命中]" in captured.out

    def test_vtt_subtitle_excluded(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Videos", "Demon Slayer Episode 1.en.vtt")
        self._make_file(tmp_path, "Songs", "Oasis - Wonderwall.mp3")

        check("Demon Slayer")
        captured = capsys.readouterr()
        assert "[未命中]" in captured.out
        assert "vtt" not in captured.out.lower()
        assert "Demon Slayer Episode 1.en.vtt" not in captured.out

    def test_mp4_uppercase_hit(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Videos", "Demo Movie.MP4")

        check("Demo Movie")
        captured = capsys.readouterr()
        assert "Demo Movie.MP4" in captured.out
        assert "[Videos]" in captured.out
        assert "[命中]" in captured.out

    def test_mp4_part_excluded(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        self._make_file(tmp_path, "Videos", "Downloaded Movie.mp4.part")
        self._make_file(tmp_path, "Songs", "Oasis - Wonderwall.mp3")

        check("Downloaded Movie")
        captured = capsys.readouterr()
        assert "[未命中]" in captured.out
        assert "Downloaded Movie.mp4.part" not in captured.out
        assert ".part" not in captured.out

    def test_directory_with_mp4_name_excluded(self, capsys, tmp_path, monkeypatch):
        self._patch_dirs(tmp_path, monkeypatch)
        (tmp_path / "Videos" / "My Video.mp4").mkdir(parents=True, exist_ok=True)
        self._make_file(tmp_path, "Songs", "Oasis - Wonderwall.mp3")

        check("My Video")
        captured = capsys.readouterr()
        assert "[未命中]" in captured.out
        assert "My Video.mp4" not in captured.out
        assert "(扫描 Songs 1 个文件)" in captured.out
        assert "Videos" not in captured.out


# ── video codec/path checks ──────────────────────

class TestExtractDownloadedPath:
    def test_prefers_last_matching_line(self, tmp_path):
        out_dir = str(tmp_path / "Videos")
        vtt_path = os.path.join(out_dir, "Subtitle.en.vtt")
        mp4_path = os.path.join(out_dir, "FP2 Highlights.mp4")
        stdout = f"[Merger] Merging formats into \"{mp4_path}\"\n{vtt_path}\n{mp4_path}\n"
        assert _extract_downloaded_path(stdout, out_dir) == mp4_path

    def test_returns_none_for_subtitle_only(self, tmp_path):
        out_dir = str(tmp_path / "Videos")
        vtt_path = os.path.join(out_dir, "Subtitle.en.vtt")
        assert _extract_downloaded_path(vtt_path + "\n", out_dir) is None

    def test_returns_none_when_no_match(self, tmp_path):
        out_dir = str(tmp_path / "Videos")
        stdout = "[download] some progress line\n[info] done\n"
        assert _extract_downloaded_path(stdout, out_dir) is None


class TestVideoCodecName:
    def test_returns_codec_and_no_error(self, tmp_path, monkeypatch):
        def mock_run(args, **kwargs):
            assert kwargs.get("timeout") == 30
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="h264\n")

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", mock_run)
        codec, error = _video_codec_name(str(tmp_path / "video.mp4"))
        assert codec == "h264"
        assert error is None

    def test_reports_missing_ffprobe(self, tmp_path, monkeypatch):
        def mock_run(args, **kwargs):
            raise FileNotFoundError("ffprobe not found")

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", mock_run)
        codec, error = _video_codec_name(str(tmp_path / "video.mp4"))
        assert codec is None
        assert "ffprobe 未安装" in error

    def test_reports_nonzero_exit(self, tmp_path, monkeypatch):
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="invalid data"
            )

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", mock_run)
        codec, error = _video_codec_name(str(tmp_path / "video.mp4"))
        assert codec is None
        assert "invalid data" in error


class TestCheckDownloadedVideoCodec:
    def test_warns_when_codec_is_not_h264(self, capsys, tmp_path, monkeypatch):
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="av1\n")

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", mock_run)
        _check_downloaded_video_codec(str(tmp_path / "video.mp4"))
        captured = capsys.readouterr()
        assert "[warn]" in captured.out
        assert "视频流为 av1" in captured.out
        assert "libx264" in captured.out
        assert "ffmpeg -i" in captured.out

    def test_quiet_when_codec_is_h264(self, capsys, tmp_path, monkeypatch):
        def mock_run(args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="h264\n")

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", mock_run)
        _check_downloaded_video_codec(str(tmp_path / "video.mp4"))
        captured = capsys.readouterr()
        assert "[warn]" not in captured.out
        assert captured.out == ""


class TestDownloadVideoIntegration:
    def test_uses_exact_path_from_ytdlp_output(self, tmp_path, monkeypatch):
        video_dir = tmp_path / "Videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setitem(_DIRS, "video", str(video_dir))

        newer_file = video_dir / "Australian GP.mp4"
        newer_file.write_text("")
        os.utime(newer_file, (1000, 1000))

        exact_path = video_dir / "FP2 Highlights.mp4"
        exact_path.write_text("")
        os.utime(exact_path, (500, 500))

        checked_paths = []

        def fake_check(path):
            checked_paths.append(path)

        monkeypatch.setattr("ai_youtube_summary.download._check_downloaded_video_codec", fake_check)
        monkeypatch.setattr(
            "ai_youtube_summary.download._ensure_downloaded_video_has_audio", lambda path: None
        )

        stdout = (
            "[download] Destination: some temporary file\n"
            f"{exact_path}\n"
        )

        def fake_run(args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout)

        monkeypatch.setattr("ai_youtube_summary.download.subprocess.run", fake_run)
        result_path = download("video", "F1 Race Highlights")

        assert checked_paths == [str(exact_path)]
        assert result_path == str(exact_path)
