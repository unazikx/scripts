{
  python312Packages,
  lib,
}:

# WARN:
# requires configured rbw
# NOT BW

python312Packages.buildPythonApplication {
  pname = baseNameOf ./.;
  version = "git";

  src = ./script.py;
  dontUnpack = true;

  propagatedBuildInputs = [ python312Packages.python ];

  format = "other";

  installPhase = ''
    install -Dm755 $src $out/bin/rbw-qutebrowser
  '';

  meta = {
    description = "Fill logins via rbw from qutebrowser";
    homepage = "https://gist.github.com/azikz/46ae13e0ea722203a13e318c871bb349";
    license = lib.licenses.wtfpl;
    platforms = [ "x86_64-linux" ];
    maintainers = with lib.maintainers; [ unazikx ];
    mainProgram = "rbw-qutebrowser";
  };
}
