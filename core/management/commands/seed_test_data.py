"""Generate a realistic development dataset.

    python manage.py seed_test_data
    python manage.py seed_test_data --users 100 --min-projects 1 --max-projects 10
    python manage.py seed_test_data --clear

SAFETY
------
Everything this command creates is identifiable, and --clear removes only that:

* Seeded users are the only users whose email ends in @launchpad.test. All of
  their projects, likes, comments, follows, bookmarks, notifications, activity
  and contest records hang off them by foreign key and go with them.
* Contests and badges have no owning user, so their primary keys are recorded
  in a manifest file written next to manage.py.
* Generated media files are all prefixed "seed_".

--clear will never delete a superuser or a staff account, never touches users
outside the @launchpad.test domain, and never drops a table or a migration.
It also refuses to delete a seeded contest that still has a participant from
outside the seeded set.

The seed password is a fixed development credential defined below. It is
deliberately never written to stdout - read it from TEST_PASSWORD in this file
when you need to log in as a seeded account.
"""

import json
import random
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from core.models import (
    Achievement,
    ActivityEvent,
    Badge,
    Certificate,
    Bookmark,
    BookmarkCollection,
    Category,
    Comment,
    Contest,
    ContestParticipant,
    ContestSubmission,
    Follow,
    Like,
    Notification,
    Profile,
    Project,
    ProjectImage,
    ProfileVisit,
    ProjectView,
    Report,
    UserBadge,
)
from core.views import refresh_leaderboards

# --- markers used to identify seeded data -----------------------------------

SEED_EMAIL_DOMAIN = "launchpad.test"
SEED_MEDIA_PREFIX = "seed_"
MANIFEST_PATH = Path(settings.BASE_DIR) / ".seed_manifest.json"

# TEST DATA ONLY. This is a development fixture credential for local seeded
# accounts. It is never used by, or valid for, anything else. Do not reuse it
# anywhere real, and do not enable this command in a deployed environment.
TEST_PASSWORD = "launchpad-dev-only-2026"

# --- source material --------------------------------------------------------

FIRST_NAMES = [
    "Aarav", "Riya", "Kabir", "Ananya", "Vihaan", "Diya", "Arjun", "Ishita",
    "Reyansh", "Meera", "Aditya", "Saanvi", "Rohan", "Aisha", "Krishna",
    "Tara", "Dev", "Nisha", "Yash", "Priya", "Karan", "Sneha", "Aryan",
    "Kavya", "Nikhil", "Pooja", "Siddharth", "Anjali", "Rahul", "Divya",
    "Manav", "Neha", "Varun", "Shreya", "Aman", "Trisha", "Ved", "Lakshmi",
    "Ishaan", "Rhea", "Om", "Simran", "Farhan", "Zoya", "Imran", "Sara",
    "Joel", "Naomi", "Ethan", "Leah",
]

LAST_NAMES = [
    "Mehta", "Sharma", "Patel", "Rao", "Iyer", "Nair", "Gupta", "Reddy",
    "Kulkarni", "Desai", "Joshi", "Bose", "Chatterjee", "Menon", "Pillai",
    "Sethi", "Bhat", "Kaur", "Singh", "Verma", "Malhotra", "Chopra",
    "Banerjee", "Ghosh", "Das", "Mishra", "Agarwal", "Kapoor", "Saxena",
    "Trivedi", "Fernandes", "D'Souza", "Thomas", "Varghese", "Khan",
]

COLLEGES = [
    "Indian Institute of Technology, Bombay",
    "Indian Institute of Technology, Delhi",
    "National Institute of Technology, Trichy",
    "Birla Institute of Technology and Science, Pilani",
    "Delhi Technological University",
    "Vellore Institute of Technology",
    "Manipal Institute of Technology",
    "College of Engineering, Pune",
    "PSG College of Technology",
    "Jadavpur University",
    "Anna University",
    "Netaji Subhas University of Technology",
]

EDUCATION = [
    "B.Tech Computer Science, 2026",
    "B.Tech Information Technology, 2027",
    "B.E. Electronics and Communication, 2026",
    "M.Tech Data Science, 2025",
    "BCA, 2027",
    "MCA, 2026",
    "B.Sc Computer Science, 2027",
    "B.Tech Mechanical Engineering, 2026",
]

SKILL_POOL = [
    "Python", "Django", "PostgreSQL", "JavaScript", "React", "TypeScript",
    "Node.js", "Flask", "FastAPI", "Docker", "Kubernetes", "AWS", "Git",
    "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "NumPy", "Figma",
    "Flutter", "Kotlin", "Swift", "C++", "Rust", "Go", "Redis", "GraphQL",
    "Tailwind CSS", "Arduino", "Raspberry Pi", "Firebase", "MongoDB",
]

BIO_TEMPLATES = [
    "{degree} student who likes turning small annoyances into working software.",
    "Building things for the campus community. Mostly {skill} at the moment.",
    "Interested in {topic}. Currently figuring out how far {skill} can be pushed.",
    "I write code, break it, and write it again. {skill} is my current obsession.",
    "Final-year student documenting everything I build so the next person has it easier.",
    "Somewhere between {skill} and {skill2}. Always up for a build weekend.",
    "I care about software that people actually use. Working on {topic} right now.",
    "Learning in public. Expect rough edges and honest write-ups.",
]

BIO_TOPICS = [
    "accessible interfaces", "applied machine learning", "developer tooling",
    "campus logistics", "open data", "embedded systems", "design systems",
    "climate tech", "education technology", "computer vision",
]

PROJECT_CONCEPTS = [
    ("Campus Navigator", "Indoor and outdoor wayfinding for a university campus, with live class-to-class routing.", "Mobile Development"),
    ("Expense Splitter", "Shared expense tracking for hostel roommates, with settlement suggestions.", "Web Development"),
    ("AI Study Assistant", "Summarises lecture notes and generates practice questions from uploaded material.", "Machine Learning & AI"),
    ("Mess Menu Predictor", "Predicts the daily mess menu and lets students rate meals over time.", "Data Science"),
    ("Portfolio Builder", "Generates a deployable developer portfolio from a structured profile.", "Web Development"),
    ("Weather Dashboard", "Regional weather visualisation with historical comparison and alerts.", "Data Science"),
    ("Task Orbit", "Keyboard-first task manager built around timeboxing rather than lists.", "Web Development"),
    ("Campus Eats", "Food ordering and pickup scheduling for on-campus outlets.", "Web Development"),
    ("Fitness Companion", "Workout logging with progressive overload tracking and rest-day guidance.", "Mobile Development"),
    ("IoT Room Monitor", "Temperature, humidity and air-quality monitoring with a live dashboard.", "IoT & Hardware"),
    ("Library Seat Finder", "Real-time occupancy map for library study spaces using cheap sensors.", "IoT & Hardware"),
    ("Code Review Buddy", "Static analysis bot that leaves review comments on student pull requests.", "Systems & Tools"),
    ("Attendance Vision", "Face-recognition attendance system with a manual override workflow.", "Machine Learning & AI"),
    ("Sign Language Translator", "Real-time hand-sign recognition translating to text on device.", "Machine Learning & AI"),
    ("Placement Tracker", "Tracks placement applications, rounds and outcomes across a batch.", "Web Development"),
    ("Lecture Notes Wiki", "Collaborative course notes with versioning and per-topic ownership.", "Web Development"),
    ("Budget Lens", "Personal finance dashboard that categorises spending from statement uploads.", "Data Science"),
    ("Retro Arcade", "Browser-based arcade with three original games and a shared leaderboard.", "Game Development"),
    ("Pixel Dungeon Clone", "Procedurally generated roguelike with permadeath and a seeded daily run.", "Game Development"),
    ("Design Tokens Kit", "A tiny design-token pipeline that outputs CSS, Figma and Tailwind configs.", "UI/UX Design"),
    ("Accessibility Auditor", "Scans a site and reports contrast, focus and landmark issues.", "UI/UX Design"),
    ("Deploy Genie", "One-command deployment helper for small Django and Flask projects.", "Systems & Tools"),
    ("Smart Irrigation", "Soil-moisture driven irrigation controller with a scheduling override.", "IoT & Hardware"),
    ("Plant Disease Detector", "Leaf-image classifier that flags common crop diseases offline.", "Machine Learning & AI"),
    ("Ride Share Campus", "Carpool matching for students commuting from the same neighbourhoods.", "Mobile Development"),
    ("Resume Parser", "Extracts structured data from resumes and scores them against a role.", "Machine Learning & AI"),
    ("Event Hub", "Club event listings with RSVP, reminders and post-event photo galleries.", "Web Development"),
    ("Sleep Tracker", "Sleep quality logging with correlation against caffeine and screen time.", "Mobile Development"),
    ("Open Data Explorer", "Interactive explorer for municipal open datasets with shareable views.", "Data Science"),
    ("Terminal Dashboard", "A TUI system dashboard with pluggable widgets and themes.", "Systems & Tools"),
]

TITLE_VARIANTS = ["", " v2", " Lite", " Pro", " Rebuild", " 2.0", " Mini", " Studio", " Next"]

DESCRIPTION_OPENERS = [
    "I built this after getting frustrated with how the existing options worked.",
    "This started as a weekend experiment and turned into something I actually use.",
    "A course project that I kept working on after the semester ended.",
    "Built with a friend over a hackathon and cleaned up afterwards.",
    "My attempt at solving a problem I ran into every single week.",
    "This is the third rewrite. The first two taught me what not to do.",
    "I wanted to understand the problem properly, so I built the whole thing from scratch.",
]

DESCRIPTION_BODIES = [
    "The hardest part was getting the data model right; everything else followed from that.",
    "Performance was the main constraint, so a lot of the work went into caching and query shape.",
    "I spent more time on the interface than the backend, which was the right call here.",
    "Testing was an afterthought at first, which I regretted. There is a real suite now.",
    "It handles the common cases well. The edge cases are documented in the README.",
    "The deployment story took longer than the feature work, which surprised me.",
    "Accessibility was a requirement from day one rather than something bolted on later.",
]

DESCRIPTION_CLOSERS = [
    "Open to feedback, especially on the architecture.",
    "Still actively working on it. Issues and suggestions welcome.",
    "Considered finished. I would build it differently now, but it works.",
    "Next up is proper offline support.",
    "The write-up in the repo explains the tradeoffs in more detail.",
    "I learned a lot building this, most of it the hard way.",
]

TAG_POOL = [
    "AI", "education", "web", "mobile", "opensource", "hackathon", "campus",
    "productivity", "health", "iot", "data", "design", "games", "tooling",
    "accessibility", "realtime", "api", "dashboard",
]

COMMENT_TEXTS = [
    "This is genuinely useful. How are you handling the offline case?",
    "Clean write-up. The architecture section answered most of my questions.",
    "I ran into the same problem last semester and gave up. Nice work sticking with it.",
    "Any plans to open source it?",
    "The interface is really tidy. Did you use a design system or build it yourself?",
    "Have you benchmarked this with a larger dataset?",
    "Bookmarking this for my own project. Thanks for documenting the tradeoffs.",
    "Small thing, but the empty state on the dashboard is a nice touch.",
    "How long did this take end to end?",
    "This would be a great fit for the innovation contest.",
    "Solid execution. The demo link made it easy to try.",
    "Curious why you went with this stack over the alternatives.",
]

REPLY_TEXTS = [
    "Thanks! Offline is on the roadmap but not there yet.",
    "Appreciate it. Repo link is in the resources section.",
    "Good question, I will add a note about that to the README.",
    "About six weeks, mostly evenings and weekends.",
    "Built it myself, though I borrowed a lot of ideas.",
    "Not yet, but I would like to before the end of term.",
]

COLLECTION_NAMES = [
    "Favorite Projects", "Inspiration", "To Try", "Web Development",
    "AI Ideas", "Final Year Ideas", "Design References", "Weekend Builds",
]

CONTEST_BLUEPRINTS = [
    {
        "title": "Winter Innovation Sprint",
        "description": "A two-week sprint to build something that makes campus life measurably better. Solo or pairs.",
        "rules": "Original work only. Must be started during the sprint window. Submit a working demo and a public repository.",
        "prize_information": "Winner receives a certificate, a featured slot on the homepage, and 100 leaderboard points.",
        "status": "completed",
        "reg_offset": -60, "sub_offset": -40, "max_participants": None,
    },
    {
        "title": "Open Data Challenge",
        "description": "Build something meaningful on top of a publicly available dataset. Analysis, tooling or visualisation all qualify.",
        "rules": "Dataset must be publicly licensed and cited. Submissions are judged on insight, clarity and reproducibility.",
        "prize_information": "Top three entries receive certificates and leaderboard points.",
        "status": "active",
        "reg_offset": 6, "sub_offset": 20, "max_participants": 40,
    },
    {
        "title": "Accessibility Build-Off",
        "description": "Design and build an interface that works well for everyone, including keyboard and screen-reader users.",
        "rules": "Entries must pass an automated accessibility audit and include a short note on the decisions made.",
        "rules_note": "",
        "status": "upcoming",
        "reg_offset": 21, "sub_offset": 45, "max_participants": 60,
        "prize_information": "Certificates for the top two entries plus a mentoring session.",
    },
    {
        "title": "Hardware Hack Weekend",
        "description": "48 hours to build something physical. Sensors, robotics, wearables or anything else with a plug.",
        "rules": "Teams of up to three. Hardware must be demonstrated live. Budget cap applies.",
        "prize_information": "Component vouchers and certificates for the winning team.",
        "status": "draft",
        "reg_offset": 40, "sub_offset": 70, "max_participants": 30,
    },
    {
        "title": "Summer Portfolio Jam",
        "description": "Ship a portfolio-quality project over the summer break and document the whole process.",
        "rules": "Weekly progress updates required. Final submission needs a demo, a repository and a write-up.",
        "prize_information": "Certificates and featured placement for standout entries.",
        "status": "completed",
        "reg_offset": -150, "sub_offset": -110, "max_participants": None,
    },
]

BADGE_BLUEPRINTS = [
    ("First Project", "Published your first LaunchPad project.", 10),
    ("Contest Winner", "Won a LaunchPad innovation contest.", 100),
    ("Top Creator", "Published ten or more projects.", 50),
    ("Community Favorite", "Received fifty likes across your work.", 40),
    ("Rising Innovator", "Gained twenty five followers.", 30),
    ("Most Viewed", "Your work passed one thousand views.", 35),
    ("Most Liked", "Held the most-liked project of the month.", 45),
]

ACHIEVEMENT_BLUEPRINTS = [
    ("Shipped in public", "Published a project with a live demo and a public repository.", 15),
    ("Consistent builder", "Published projects in three consecutive months.", 25),
    ("Helpful reviewer", "Left twenty constructive comments on other students' work.", 20),
    ("Documented thoroughly", "Shipped a project with complete written documentation.", 10),
    ("Contest finalist", "Reached the final round of an innovation contest.", 40),
]

REPORT_REASONS = ["spam", "plagiarism", "inappropriate", "misleading", "broken_links"]


# ---------------------------------------------------------------------------
# image generation
# ---------------------------------------------------------------------------

PALETTE = [
    ((37, 99, 235), (219, 234, 254)),
    ((15, 155, 136), (217, 245, 239)),
    ((161, 98, 7), (254, 243, 199)),
    ((190, 18, 60), (255, 228, 230)),
    ((109, 40, 217), (237, 228, 253)),
    ((8, 17, 31), (196, 206, 219)),
    ((23, 38, 58), (220, 227, 236)),
]


def write_image(relative_dir, filename, size, label, rng):
    """Write a small flat-colour PNG and return its media-relative path."""
    dark, light = rng.choice(PALETTE)
    image = Image.new("RGB", size, light)
    draw = ImageDraw.Draw(image)

    # A couple of flat blocks keeps the PNG tiny while still looking distinct.
    width, height = size
    draw.rectangle([0, 0, width, int(height * 0.42)], fill=dark)
    draw.rectangle(
        [int(width * 0.08), int(height * 0.55), int(width * 0.42), int(height * 0.62)],
        fill=dark,
    )
    if label:
        draw.text((int(width * 0.08), int(height * 0.14)), label[:2].upper(), fill=light)

    target_dir = Path(settings.MEDIA_ROOT) / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    (target_dir / filename).write_bytes(buffer.getvalue())

    return f"{relative_dir}/{filename}"


def remove_seeded_media():
    """Delete only files this command generated."""
    removed = 0
    media_root = Path(settings.MEDIA_ROOT)

    for sub in ["avatars", "covers", "projects"]:
        directory = media_root / sub
        if not directory.exists():
            continue
        for path in directory.glob(f"{SEED_MEDIA_PREFIX}*"):
            path.unlink()
            removed += 1

    return removed


# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Create (or remove) a realistic development dataset. Never touches real accounts."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=100, help="Number of users to create (default 100).")
        parser.add_argument("--min-projects", type=int, default=1, help="Minimum projects per user (default 1).")
        parser.add_argument("--max-projects", type=int, default=10, help="Maximum projects per user (default 10).")
        parser.add_argument("--seed", type=int, default=20260824, help="Random seed for reproducible data.")
        parser.add_argument("--no-media", action="store_true", help="Skip generating avatar/cover/project images.")
        parser.add_argument("--clear", action="store_true", help="Remove ONLY data created by this command.")

    # -- entry point --------------------------------------------------------

    def handle(self, *args, **options):
        if options["clear"]:
            return self.clear(options)

        users = options["users"]
        low = options["min_projects"]
        high = options["max_projects"]

        if users < 1:
            raise CommandError("--users must be at least 1.")
        if low < 0 or high < low:
            raise CommandError("--min-projects must be >= 0 and <= --max-projects.")
        if not Category.objects.exists():
            raise CommandError(
                "No categories exist. Run `python manage.py migrate` first so "
                "migration 0009 can seed the taxonomy."
            )

        rng = random.Random(options["seed"])
        self.rng = rng
        self.make_media = not options["no_media"]

        self.stdout.write("Seeding development data. Existing accounts are not touched.")

        with transaction.atomic():
            people = self.create_users(users, rng)
            projects = self.create_projects(people, low, high, rng)
            self.create_project_images(projects, rng)
            self.create_follows(people, rng)
            likes, bookmarks, collections = self.create_engagement(people, projects, rng)
            comments = self.create_comments(people, projects, rng)
            self.create_traffic(people, projects, rng)
            contests, participants, submissions = self.create_contests(people, projects, rng)
            self.create_gamification(people, projects, rng)
            self.create_reports(people, projects, rng)
            self.create_activity_and_notifications(
                people, projects, likes, comments, rng
            )

        # Leaderboards are computed by the real application logic, never faked.
        refresh_leaderboards()

        self.write_manifest(contests, submissions)
        self.report_summary()

    # -- creation steps -----------------------------------------------------

    def create_users(self, count, rng):
        self.stdout.write(f"  users            ... ", ending="")

        # Hash the shared development password once. Hashing it 100 times would
        # dominate the runtime and buys nothing for a fixture credential.
        hashed = make_password(TEST_PASSWORD)

        existing = set(User.objects.values_list("username", flat=True))
        pending = []
        used = set()

        index = 0
        while len(pending) < count:
            index += 1
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            base = f"{first}.{last}".lower().replace("'", "")
            username = f"{base}{index:03d}"

            if username in existing or username in used:
                continue
            used.add(username)

            pending.append(
                User(
                    username=username,
                    first_name=first,
                    last_name=last,
                    email=f"{username}@{SEED_EMAIL_DOMAIN}",
                    password=hashed,
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                )
            )

        people = User.objects.bulk_create(pending)

        # Spread joining dates across the last two years.
        now = timezone.now()
        for person in people:
            person.date_joined = now - timedelta(days=rng.randint(20, 730))
        User.objects.bulk_update(people, ["date_joined"])

        profiles = []
        for person in people:
            skills = rng.sample(SKILL_POOL, rng.randint(3, 8))
            template = rng.choice(BIO_TEMPLATES)
            bio = template.format(
                degree=rng.choice(EDUCATION).split(",")[0],
                skill=skills[0],
                skill2=skills[1] if len(skills) > 1 else "design",
                topic=rng.choice(BIO_TOPICS),
            )
            handle = person.username.replace(".", "")

            profiles.append(
                Profile(
                    user=person,
                    display_name=f"{person.first_name} {person.last_name}",
                    bio=bio,
                    college=rng.choice(COLLEGES),
                    education=rng.choice(EDUCATION),
                    skills=", ".join(skills),
                    portfolio_url=f"https://{handle}.example.test" if rng.random() < 0.45 else "",
                    github_url=f"https://github.test/{handle}" if rng.random() < 0.7 else "",
                    linkedin_url=f"https://linkedin.test/in/{handle}" if rng.random() < 0.5 else "",
                    twitter_url=f"https://social.test/{handle}" if rng.random() < 0.25 else "",
                )
            )

        Profile.objects.bulk_create(profiles)

        if self.make_media:
            # Not every profile has pictures - missing-image handling needs to
            # stay exercised.
            for profile in profiles:
                changed = []
                if rng.random() < 0.75:
                    profile.avatar = write_image(
                        "avatars",
                        f"{SEED_MEDIA_PREFIX}avatar_{profile.user.username}.png",
                        (200, 200),
                        profile.user.first_name,
                        rng,
                    )
                    changed.append("avatar")
                if rng.random() < 0.45:
                    profile.cover_image = write_image(
                        "covers",
                        f"{SEED_MEDIA_PREFIX}cover_{profile.user.username}.png",
                        (800, 260),
                        profile.user.first_name,
                        rng,
                    )
                    changed.append("cover_image")
            Profile.objects.bulk_update(profiles, ["avatar", "cover_image"])

        self.stdout.write(self.style.SUCCESS(f"{len(people)}"))
        return people

    def create_projects(self, people, low, high, rng):
        self.stdout.write(f"  projects         ... ", ending="")

        categories = {c.name: c for c in Category.objects.all()}
        fallback = categories.get("Other") or next(iter(categories.values()))
        now = timezone.now()

        pending = []
        timestamps = []

        for person in people:
            for _ in range(rng.randint(low, high)):
                concept, summary, category_name = rng.choice(PROJECT_CONCEPTS)
                title = f"{concept}{rng.choice(TITLE_VARIANTS)}"

                description = " ".join([
                    rng.choice(DESCRIPTION_OPENERS),
                    summary,
                    rng.choice(DESCRIPTION_BODIES),
                    rng.choice(DESCRIPTION_CLOSERS),
                ])

                status, visibility = self.pick_state(rng)
                technologies = ", ".join(rng.sample(SKILL_POOL, rng.randint(2, 6)))
                handle = person.username.replace(".", "")
                slug = concept.lower().replace(" ", "-")

                pending.append(
                    Project(
                        owner=person,
                        category=categories.get(category_name, fallback),
                        title=title,
                        short_description=summary[:280],
                        description=description,
                        technologies=technologies,
                        tags=", ".join(rng.sample(TAG_POOL, rng.randint(2, 4))),
                        demo_url=f"https://{slug}.example.test" if rng.random() < 0.55 else "",
                        repository_url=f"https://github.test/{handle}/{slug}" if rng.random() < 0.8 else "",
                        documentation_url=f"https://docs.example.test/{slug}" if rng.random() < 0.2 else "",
                        visibility=visibility,
                        status=status,
                        stage=rng.choice(["prototype", "ongoing", "completed"]),
                        views_count=0,
                    )
                )
                timestamps.append(now - timedelta(days=rng.randint(1, 540), hours=rng.randint(0, 23)))

        projects = Project.objects.bulk_create(pending)

        # created_at is auto_now_add, so backdate it after the fact.
        for project, created in zip(projects, timestamps):
            project.created_at = created
        Project.objects.bulk_update(projects, ["created_at"])

        # A small number of published public projects are featured.
        featured = [
            p for p in projects
            if p.status == "published" and p.visibility == "public" and rng.random() < 0.04
        ]
        for project in featured:
            project.featured = True
            project.featured_at = now - timedelta(days=rng.randint(1, 90))
        if featured:
            Project.objects.bulk_update(featured, ["featured", "featured_at"])

        self.stdout.write(self.style.SUCCESS(f"{len(projects)}"))
        return projects

    def pick_state(self, rng):
        """Realistic status/visibility mix so visibility rules stay testable."""
        roll = rng.random()
        if roll < 0.70:
            return "published", "public"
        if roll < 0.85:
            return "draft", "private"
        if roll < 0.95:
            return "published", "private"
        return "draft", "public"

    def create_project_images(self, projects, rng):
        self.stdout.write(f"  project images   ... ", ending="")

        if not self.make_media:
            self.stdout.write(self.style.WARNING("skipped (--no-media)"))
            return []

        pending = []
        for project in projects:
            if rng.random() > 0.45:
                continue
            for index in range(rng.randint(1, 2)):
                path = write_image(
                    "projects",
                    f"{SEED_MEDIA_PREFIX}p{project.pk}_{index}.png",
                    (640, 400),
                    project.title,
                    rng,
                )
                pending.append(
                    ProjectImage(
                        project=project,
                        image=path,
                        caption=rng.choice([
                            "Dashboard view", "Mobile layout", "Onboarding flow",
                            "Results screen", "Architecture diagram", "",
                        ]),
                    )
                )

        images = ProjectImage.objects.bulk_create(pending)
        self.stdout.write(self.style.SUCCESS(f"{len(images)}"))
        return images

    def create_follows(self, people, rng):
        self.stdout.write(f"  follows          ... ", ending="")

        pending = []
        seen = set()

        for person in people:
            candidates = rng.sample(people, min(len(people), rng.randint(2, 18)))
            for target in candidates:
                if target.pk == person.pk:
                    continue  # no self-follow
                key = (person.pk, target.pk)
                if key in seen:
                    continue  # respects unique_follower_following
                seen.add(key)
                pending.append(Follow(follower=person, following=target))

        follows = Follow.objects.bulk_create(pending)
        self.stdout.write(self.style.SUCCESS(f"{len(follows)}"))
        return follows

    def create_engagement(self, people, projects, rng):
        self.stdout.write(f"  collections      ... ", ending="")

        collections = []
        for person in people:
            if rng.random() > 0.55:
                continue
            for name in rng.sample(COLLECTION_NAMES, rng.randint(1, 3)):
                collections.append(
                    BookmarkCollection(
                        user=person,
                        name=name,
                        description=rng.choice([
                            "Things worth coming back to.",
                            "Reference material for my own build.",
                            "Shortlist for next semester.",
                            "",
                        ]),
                    )
                )
        collections = BookmarkCollection.objects.bulk_create(collections)
        self.stdout.write(self.style.SUCCESS(f"{len(collections)}"))

        by_user = {}
        for collection in collections:
            by_user.setdefault(collection.user_id, []).append(collection)

        # Only publicly visible work can realistically be liked or saved.
        discoverable = [
            p for p in projects
            if p.status == "published" and p.visibility == "public"
        ]

        self.stdout.write(f"  likes            ... ", ending="")
        like_pending = []
        seen_likes = set()
        for person in people:
            sample = rng.sample(discoverable, min(len(discoverable), rng.randint(0, 35)))
            for project in sample:
                if project.owner_id == person.pk:
                    continue
                key = (person.pk, project.pk)
                if key in seen_likes:
                    continue  # respects unique_user_project_like
                seen_likes.add(key)
                like_pending.append(Like(user=person, project=project))
        likes = Like.objects.bulk_create(like_pending)
        self.stdout.write(self.style.SUCCESS(f"{len(likes)}"))

        self.stdout.write(f"  bookmarks        ... ", ending="")
        bookmark_pending = []
        seen_bookmarks = set()
        for person in people:
            sample = rng.sample(discoverable, min(len(discoverable), rng.randint(0, 14)))
            owned = by_user.get(person.pk, [])
            for project in sample:
                if project.owner_id == person.pk:
                    continue
                key = (person.pk, project.pk)
                if key in seen_bookmarks:
                    continue  # respects unique_user_project_bookmark
                seen_bookmarks.add(key)

                # Some bookmarks stay unfiled, which keeps the null-collection
                # path that used to 500 exercised by real data.
                collection = rng.choice(owned) if owned and rng.random() < 0.6 else None
                bookmark_pending.append(
                    Bookmark(user=person, project=project, collection=collection)
                )
        bookmarks = Bookmark.objects.bulk_create(bookmark_pending)
        self.stdout.write(self.style.SUCCESS(f"{len(bookmarks)}"))

        return likes, bookmarks, collections

    def create_comments(self, people, projects, rng):
        self.stdout.write(f"  comments         ... ", ending="")

        discoverable = [
            p for p in projects
            if p.status == "published" and p.visibility == "public"
        ]
        if not discoverable:
            self.stdout.write(self.style.SUCCESS("0"))
            return []

        top_level = []
        for project in discoverable:
            for _ in range(rng.randint(0, 4)):
                author = rng.choice(people)
                if author.pk == project.owner_id:
                    continue
                top_level.append(
                    Comment(
                        user=author,
                        project=project,
                        content=rng.choice(COMMENT_TEXTS),
                    )
                )
        top_level = Comment.objects.bulk_create(top_level)

        # Owners reply to a subset of the comments on their own work.
        owners = {p.pk: p.owner for p in discoverable}
        replies = []
        for comment in top_level:
            if rng.random() > 0.3:
                continue
            replies.append(
                Comment(
                    user=owners[comment.project_id],
                    project_id=comment.project_id,
                    parent=comment,
                    content=rng.choice(REPLY_TEXTS),
                )
            )
        replies = Comment.objects.bulk_create(replies)

        self.stdout.write(self.style.SUCCESS(f"{len(top_level) + len(replies)}"))
        return list(top_level) + list(replies)

    def create_traffic(self, people, projects, rng):
        self.stdout.write(f"  views / visits   ... ", ending="")

        discoverable = [
            p for p in projects
            if p.status == "published" and p.visibility == "public"
        ]

        view_pending = []
        counts = {}
        for project in discoverable:
            total = rng.randint(0, 60)
            counts[project.pk] = total
            for _ in range(min(total, 12)):  # store a sample of the events
                visitor = rng.choice(people) if rng.random() < 0.7 else None
                view_pending.append(
                    ProjectView(
                        project=project,
                        visitor=visitor,
                        session_key="" if visitor else f"seedsess{rng.randint(1000, 9999)}",
                    )
                )
        ProjectView.objects.bulk_create(view_pending)

        # Keep the denormalised counter consistent with something plausible.
        for project in discoverable:
            project.views_count = counts.get(project.pk, 0)
        if discoverable:
            Project.objects.bulk_update(discoverable, ["views_count"])

        visit_pending = []
        for person in people:
            for _ in range(rng.randint(0, 20)):
                visitor = rng.choice(people) if rng.random() < 0.75 else None
                if visitor and visitor.pk == person.pk:
                    continue
                visit_pending.append(
                    ProfileVisit(
                        profile_user=person,
                        visitor=visitor,
                        session_key="" if visitor else f"seedsess{rng.randint(1000, 9999)}",
                    )
                )
        ProfileVisit.objects.bulk_create(visit_pending)

        self.stdout.write(
            self.style.SUCCESS(f"{len(view_pending)} views / {len(visit_pending)} visits")
        )

    def create_contests(self, people, projects, rng):
        self.stdout.write(f"  contests         ... ", ending="")

        now = timezone.now()
        contests = []
        for blueprint in CONTEST_BLUEPRINTS:
            contests.append(
                Contest(
                    title=blueprint["title"],
                    description=blueprint["description"],
                    rules=blueprint["rules"],
                    registration_deadline=now + timedelta(days=blueprint["reg_offset"]),
                    submission_deadline=now + timedelta(days=blueprint["sub_offset"]),
                    max_participants=blueprint["max_participants"],
                    prize_information=blueprint["prize_information"],
                    status=blueprint["status"],
                )
            )
        contests = Contest.objects.bulk_create(contests)

        # Only projects that are genuinely public and published are entered.
        # Submitting private work is the open P1 defect; the seeder does not
        # create data that depends on it.
        eligible = {}
        for project in projects:
            if project.status == "published" and project.visibility == "public":
                eligible.setdefault(project.owner_id, []).append(project)

        participants = []
        for contest in contests:
            if contest.status == "draft":
                continue  # an unpublished contest has no entrants yet
            pool = rng.sample(people, min(len(people), rng.randint(8, 30)))
            if contest.max_participants:
                pool = pool[: contest.max_participants]
            for person in pool:
                participants.append(
                    ContestParticipant(contest=contest, user=person)
                )
        participants = ContestParticipant.objects.bulk_create(participants)

        submissions = []
        used = set()
        for participant in participants:
            owned = eligible.get(participant.user_id)
            if not owned or rng.random() > 0.6:
                continue
            key = (participant.contest_id, participant.pk)
            if key in used:
                continue  # respects unique_contest_participant_submission
            used.add(key)
            project = rng.choice(owned)
            submissions.append(
                ContestSubmission(
                    contest_id=participant.contest_id,
                    participant=participant,
                    project=project,
                    submission_title=project.title,
                    description=rng.choice(DESCRIPTION_CLOSERS),
                    status="submitted",
                )
            )
        submissions = ContestSubmission.objects.bulk_create(submissions)

        # Completed contests get judged results.
        completed_ids = {c.pk for c in contests if c.status == "completed"}
        judged = [s for s in submissions if s.contest_id in completed_ids]
        by_contest = {}
        for submission in judged:
            by_contest.setdefault(submission.contest_id, []).append(submission)

        graded = []
        for entries in by_contest.values():
            rng.shuffle(entries)
            for position, submission in enumerate(entries):
                if position == 0:
                    submission.status = "winner"
                    submission.score = rng.randint(90, 99)
                elif position == 1:
                    submission.status = "runner_up"
                    submission.score = rng.randint(80, 89)
                elif rng.random() < 0.25:
                    submission.status = "rejected"
                    submission.score = rng.randint(30, 55)
                else:
                    submission.status = "under_review"
                    submission.score = rng.randint(55, 85)
                graded.append(submission)
        if graded:
            ContestSubmission.objects.bulk_update(graded, ["status", "score"])

        # Winners receive a certificate, mirroring what review_submission does.
        certificates = [
            Certificate(
                submission=submission,
                certificate_number=f"LP-{submission.pk:06d}",
            )
            for submission in graded
            if submission.status == "winner"
        ]
        Certificate.objects.bulk_create(certificates)

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(contests)} / {len(participants)} participants / {len(submissions)} submissions"
            )
        )
        return contests, participants, submissions

    def create_gamification(self, people, projects, rng):
        self.stdout.write(f"  badges           ... ", ending="")

        badges = []
        for name, description, points in BADGE_BLUEPRINTS:
            badge, _ = Badge.objects.get_or_create(
                name=name,
                defaults={"description": description, "points": points},
            )
            badges.append(badge)

        pending = []
        seen = set()
        for person in people:
            for badge in rng.sample(badges, rng.randint(0, 3)):
                key = (person.pk, badge.pk)
                if key in seen:
                    continue  # respects unique_user_badge
                seen.add(key)
                pending.append(UserBadge(user=person, badge=badge))
        user_badges = UserBadge.objects.bulk_create(pending)

        achievements = []
        for person in people:
            if rng.random() > 0.4:
                continue
            for title, description, points in rng.sample(
                ACHIEVEMENT_BLUEPRINTS, rng.randint(1, 2)
            ):
                achievements.append(
                    Achievement(
                        user=person,
                        title=title,
                        description=description,
                        points=points,
                    )
                )
        Achievement.objects.bulk_create(achievements)

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(badges)} / {len(user_badges)} awarded / {len(achievements)} achievements"
            )
        )
        self.badge_pks = [b.pk for b in badges]

    def create_reports(self, people, projects, rng):
        self.stdout.write(f"  reports          ... ", ending="")

        discoverable = [
            p for p in projects
            if p.status == "published" and p.visibility == "public"
        ]
        pending = []
        if discoverable:
            for _ in range(min(len(discoverable), rng.randint(6, 20))):
                project = rng.choice(discoverable)
                reporter = rng.choice(people)
                if reporter.pk == project.owner_id:
                    continue
                pending.append(
                    Report(
                        reporter=reporter,
                        reported_user=project.owner,
                        project=project,
                        reason=rng.choice(REPORT_REASONS),
                        description="Flagged during development seeding for moderation testing.",
                        status=rng.choice(["open", "open", "reviewing", "dismissed"]),
                    )
                )
        reports = Report.objects.bulk_create(pending)
        self.stdout.write(self.style.SUCCESS(f"{len(reports)}"))

    def create_activity_and_notifications(self, people, projects, likes, comments, rng):
        self.stdout.write(f"  activity / inbox ... ", ending="")

        events = []
        notifications = []

        published = [p for p in projects if p.status == "published"]
        for project in published:
            events.append(
                ActivityEvent(
                    user=project.owner,
                    actor=project.owner,
                    project=project,
                    event_type="project_published",
                    points=10,
                )
            )

        for like in likes:
            events.append(
                ActivityEvent(
                    user_id=like.project.owner_id,
                    actor_id=like.user_id,
                    project_id=like.project_id,
                    event_type="like_received",
                    points=1,
                )
            )
            if rng.random() < 0.35:
                notifications.append(
                    Notification(
                        recipient_id=like.project.owner_id,
                        sender_id=like.user_id,
                        project_id=like.project_id,
                        notification_type="like",
                        message=f"{like.user.username} liked your project {like.project.title}."[:255],
                        is_read=rng.random() < 0.6,
                    )
                )

        for comment in comments:
            if comment.parent_id is not None:
                continue
            events.append(
                ActivityEvent(
                    user_id=comment.project.owner_id,
                    actor_id=comment.user_id,
                    project_id=comment.project_id,
                    event_type="comment_received",
                    points=1,
                )
            )
            if rng.random() < 0.4:
                notifications.append(
                    Notification(
                        recipient_id=comment.project.owner_id,
                        sender_id=comment.user_id,
                        project_id=comment.project_id,
                        notification_type="comment",
                        message=f"{comment.user.username} commented on {comment.project.title}."[:255],
                        is_read=rng.random() < 0.5,
                    )
                )

        for follow in Follow.objects.select_related("follower", "following"):
            events.append(
                ActivityEvent(
                    user_id=follow.following_id,
                    actor_id=follow.follower_id,
                    event_type="follow_received",
                    points=2,
                )
            )
            if rng.random() < 0.3:
                notifications.append(
                    Notification(
                        recipient_id=follow.following_id,
                        sender_id=follow.follower_id,
                        notification_type="follow",
                        message=f"{follow.follower.username} started following you."[:255],
                        is_read=rng.random() < 0.55,
                    )
                )

        for user_badge in UserBadge.objects.select_related("badge", "user"):
            events.append(
                ActivityEvent(
                    user_id=user_badge.user_id,
                    event_type="badge_awarded",
                    points=user_badge.badge.points,
                )
            )

        for submission in ContestSubmission.objects.filter(
            status="winner",
        ).select_related("participant", "project", "contest"):
            events.append(
                ActivityEvent(
                    user_id=submission.participant.user_id,
                    project_id=submission.project_id,
                    contest_id=submission.contest_id,
                    event_type="contest_winner",
                    points=100,
                )
            )
            notifications.append(
                Notification(
                    recipient_id=submission.participant.user_id,
                    project_id=submission.project_id,
                    notification_type="contest_result",
                    message=f"Your submission won {submission.contest.title}."[:255],
                    is_read=False,
                )
            )

        for project in projects:
            if project.featured:
                events.append(
                    ActivityEvent(
                        user=project.owner,
                        project=project,
                        event_type="featured_project",
                        points=25,
                    )
                )

        ActivityEvent.objects.bulk_create(events)
        Notification.objects.bulk_create(notifications)

        self.stdout.write(
            self.style.SUCCESS(f"{len(events)} events / {len(notifications)} notifications")
        )

    # -- manifest -----------------------------------------------------------

    def write_manifest(self, contests, submissions):
        """Record the objects that --clear cannot find via user cascade."""
        MANIFEST_PATH.write_text(
            json.dumps(
                {
                    "created_at": timezone.now().isoformat(),
                    "email_domain": SEED_EMAIL_DOMAIN,
                    "media_prefix": SEED_MEDIA_PREFIX,
                    "contest_ids": [c.pk for c in contests],
                    "badge_ids": getattr(self, "badge_pks", []),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- teardown -----------------------------------------------------------

    def clear(self, options):
        seeded = User.objects.filter(
            email__iendswith=f"@{SEED_EMAIL_DOMAIN}",
        ).exclude(is_superuser=True).exclude(is_staff=True)

        count = seeded.count()
        if not count and not MANIFEST_PATH.exists():
            self.stdout.write(self.style.WARNING("Nothing to clear - no seeded data found."))
            return

        self.stdout.write(
            f"Removing {count} seeded account(s) and everything owned by them."
        )
        self.stdout.write("Superusers, staff and all other accounts are left untouched.")

        manifest = {}
        if MANIFEST_PATH.exists():
            try:
                manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.stdout.write(
                    self.style.WARNING("  manifest unreadable - contests/badges left in place")
                )

        with transaction.atomic():
            # Cascade removes projects, likes, comments, follows, bookmarks,
            # collections, notifications, activity, views, visits, contest
            # participation, submissions, certificates, badges and reports.
            deleted, _ = seeded.delete()
            self.stdout.write(f"  rows removed by cascade: {deleted}")

            for contest in Contest.objects.filter(pk__in=manifest.get("contest_ids", [])):
                remaining = contest.participants.count()
                if remaining:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  keeping contest {contest.title!r}: "
                            f"{remaining} participant(s) from outside the seeded set"
                        )
                    )
                    continue
                contest.delete()

            for badge in Badge.objects.filter(pk__in=manifest.get("badge_ids", [])):
                if badge.earned_by.exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"  keeping badge {badge.name!r}: still awarded to a real account"
                        )
                    )
                    continue
                badge.delete()

        removed_files = remove_seeded_media()
        self.stdout.write(f"  media files removed: {removed_files}")

        if MANIFEST_PATH.exists():
            MANIFEST_PATH.unlink()

        self.stdout.write(self.style.SUCCESS("Seeded data cleared."))
        self.report_summary()

    # -- summary ------------------------------------------------------------

    def report_summary(self):
        rows = [
            ("Users", User.objects.count()),
            ("Profiles", Profile.objects.count()),
            ("Categories", Category.objects.count()),
            ("Projects", Project.objects.count()),
            ("Project Images", ProjectImage.objects.count()),
            ("Likes", Like.objects.count()),
            ("Bookmarks", Bookmark.objects.count()),
            ("Collections", BookmarkCollection.objects.count()),
            ("Follows", Follow.objects.count()),
            ("Comments", Comment.objects.count()),
            ("Notifications", Notification.objects.count()),
            ("Contests", Contest.objects.count()),
            ("Participants", ContestParticipant.objects.count()),
            ("Submissions", ContestSubmission.objects.count()),
            ("Certificates", Certificate.objects.count()),
            ("Badges", Badge.objects.count()),
            ("UserBadges", UserBadge.objects.count()),
            ("Achievements", Achievement.objects.count()),
            ("ActivityEvents", ActivityEvent.objects.count()),
            ("ProjectViews", ProjectView.objects.count()),
            ("ProfileVisits", ProfileVisit.objects.count()),
            ("Reports", Report.objects.count()),
        ]

        self.stdout.write("")
        self.stdout.write("Database totals")
        self.stdout.write("-" * 34)
        for label, value in rows:
            self.stdout.write(f"{label:<18} {value:>14,}")
        self.stdout.write("")
