version = "1.1.3"

def get_version():
    version_split = version.split(".")
    spec_version = (
        (10000 * int(version_split[0]))
        + (100 * int(version_split[1]))
        + (1 * int(version_split[2]))
    )
    return spec_version