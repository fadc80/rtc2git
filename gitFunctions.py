import os
from datetime import datetime
import re

import shouter
import shell
import configuration


class Initializer:
    def __init__(self):
        config = configuration.get()
        self.repoName = config.gitRepoName
        self.clonedRepoName = config.clonedGitRepoName
        self.author = config.user

    @staticmethod
    def createignore():
        newline = "\n"
        git_ignore = ".gitignore"

        if not os.path.exists(git_ignore):
            with open(git_ignore, "w") as ignore:
                ignore.write(".jazz5" + newline)
                ignore.write(".metadata" + newline)
                ignore.write(".jazzShed" + newline)
            shell.execute("git add " + git_ignore)
            shell.execute("git commit -m %s -q" % shell.quote("Add .gitignore"))

    @staticmethod
    def createattributes():
        """
        create a .gitattributes file (if so specified and not yet present)
        """
        config = configuration.get()
        if len(config.gitattributes) > 0:
            newline = "\n"
            gitattribues = ".gitattributes"
            if not os.path.exists(gitattribues):
                with open(gitattribues, "w") as attributes:
                    for line in config.gitattributes:
                        attributes.write(line + newline)
                shell.execute("git add " + gitattribues)
                shell.execute("git commit -m %s -q" % shell.quote("Add .gitattributes"))

    def initalize(self):
        self.createrepo()
        self.preparerepo()

    @staticmethod
    def preparerepo():
        Initializer.setgitconfigs()
        Initializer.createignore()
        Initializer.createattributes()

    def createrepo(self):
        shell.execute("git init --bare " + self.repoName)
        shouter.shout("Repository was created in " + os.getcwd())
        shell.execute("git clone " + self.repoName)
        os.chdir(self.clonedRepoName)

    @staticmethod
    def setgitconfigs():
        shell.execute("git config push.default current")
        shell.execute("git config core.ignorecase false")
        shouter.shout("Set core.ignorecase to false")

    @staticmethod
    def initialcommit():
        shouter.shout("Initial git add")
        shell.execute("git add -A", os.devnull)
        shouter.shout("Finished initial git add, starting commit")
        shell.execute("git commit -m %s -q" % shell.quote("Initial Commit"))
        shouter.shout("Finished initial commit")


class Commiter:
    commitcounter = 0
    isattachedtoaworkitemregex = re.compile("^\d*:.*-")
    findignorepatternregex = re.compile("\{([^\{\}]*)\}")

    @staticmethod
    def addandcommit(changeentry):
        Commiter.handleignore()
        Commiter.replaceauthor(changeentry.author, changeentry.email)
        shell.execute("git add -A")

        Commiter.handle_captitalization_filename_changes()

        shell.execute(Commiter.getcommitcommand(changeentry))
        Commiter.commitcounter += 1
        if Commiter.commitcounter is 30:
            shouter.shout("30 Commits happend, push current branch to avoid out of memory")
            Commiter.pushbranch("")
            Commiter.commitcounter = 0
        shouter.shout("Commited change in local git repository")

    @staticmethod
    def handle_captitalization_filename_changes():
        sandbox = os.path.join(configuration.get().workDirectory, configuration.get().clonedGitRepoName)
        lines = shell.getoutput("git status -z")
        for newfilerelativepath in Commiter.splitoutputofgitstatusz(lines, "A  "):
            directoryofnewfile = os.path.dirname(os.path.join(sandbox, newfilerelativepath))
            newfilename = os.path.basename(newfilerelativepath)
            cwd = os.getcwd()
            os.chdir(directoryofnewfile)
            files = shell.getoutput("git ls-files")
            for previousFileName in files:
                was_same_file_name = newfilename.lower() == previousFileName.lower()
                file_was_renamed = newfilename != previousFileName

                if was_same_file_name and file_was_renamed:
                    shell.execute("git rm --cached %s" % previousFileName)
            os.chdir(cwd)

    @staticmethod
    def getcommitcommand(changeentry):
        comment = Commiter.getcommentwithprefix(changeentry.comment)
        return "git commit -m %s --date %s --author=%s" \
               % (shell.quote(comment), shell.quote(changeentry.date), changeentry.getgitauthor())

    @staticmethod
    def getcommentwithprefix(comment):
        prefix = configuration.get().commitmessageprefix

        if prefix and Commiter.isattachedtoaworkitemregex.match(comment):
            return prefix + comment
        return comment

    @staticmethod
    def replaceauthor(author, email):
        shell.execute("git config --replace-all user.name " + shell.quote(author))
        shell.execute("git config --replace-all user.email " + email)

    @staticmethod
    def checkbranchname(branchname):
        exitcode = shell.execute("git check-ref-format --normalize refs/heads/" + branchname)
        if exitcode is 0:
            return True
        else:
            return False

    @staticmethod
    def branch(branchname):
        branchexist = shell.execute("git show-ref --verify --quiet refs/heads/" + branchname)
        if branchexist is 0:
            Commiter.checkout(branchname)
        else:
            shell.execute("git checkout -b " + branchname)

    @staticmethod
    def pushbranch(branchname, force=False):
        if branchname:
            shouter.shout("Push of branch " + branchname)
        if force:
            return shell.execute("git push -f origin " + branchname)
        else:
            return shell.execute("git push origin " + branchname)

    @staticmethod
    def pushmaster():
        Commiter.pushbranch("master")

    @staticmethod
    def checkout(branchname):
        shell.execute("git checkout " + branchname)

    @staticmethod
    def renamebranch(oldname, newname):
        return shell.execute("git branch -m %s %s" % (oldname, newname))

    @staticmethod
    def copybranch(existingbranchname, newbranchname):
        return shell.execute("git branch %s %s" % (newbranchname, existingbranchname))

    @staticmethod
    def promotebranchtomaster(branchname):
        master = "master"
        masterename = Commiter.renamebranch(master, "masterRenamedAt_" + datetime.now().strftime('%Y%m%d_%H%M%S'))
        copybranch = Commiter.copybranch(branchname, master)

        if masterename is 0 and copybranch is 0:
            return Commiter.pushbranch(master, True)
        else:
            shouter.shout("Branch %s couldnt get renamed to master, please do that on your own" % branchname)
            return 1  # branch couldnt get renamed

    @staticmethod
    def handleignore():
        """
        check untracked files and handle both global and local ignores
        """
        # make sure we see all untracked files:
        strippedlines = shell.getoutput("git status --untracked-files=all -z")
        repositoryfiles = Commiter.splitoutputofgitstatusz(strippedlines)
        Commiter.ignoreextensions(repositoryfiles)
        Commiter.ignorejazzignore(repositoryfiles)

    @staticmethod
    def ignoreextensions(repositoryfiles):
        """
        add files with extensions to be ignored to the global .gitignore
        """
        ignorefileextensions = configuration.get().ignorefileextensions
        if len(ignorefileextensions) > 0:
            Commiter.ignore(ExtensionFilter.match(repositoryfiles, ignorefileextensions))

    @staticmethod
    def ignore(filelines):
        """
        append the file lines to the toplevel .gitignore
        :param filelines: a list of newline terminated file names to be ignored
        """
        if len(filelines) > 0:
            with open(".gitignore", "a") as ignore:
                ignore.writelines(filelines)

    @staticmethod
    def splitoutputofgitstatusz(lines, filterprefix=None):
        """
        Split the output of  'git status -z' into single files

        :param lines: the output line(s) from the command
        :param filterprefix: if given, only the files of those entries matching the prefix will be returned
        :return: a list of repository files with status changes
        """
        repositoryfiles = []
        for line in lines:                           # expect exactly one line
            entries = line.split(sep='\x00')         # ascii 0 is the delimiter
            for entry in entries:
                entry = entry.strip()
                if len(entry) > 0:
                    if not filterprefix or entry.startswith(filterprefix):
                        start = entry.find(' ')
                        if 1 <= start <= 2:
                            repositoryfile = entry[3:]   # output is formatted
                        else:
                            repositoryfile = entry       # file on a single line (e.g. rename continuation)
                        repositoryfiles.append(repositoryfile)
        return repositoryfiles

    @staticmethod
    def translatejazzignore(jazzignorelines):
        """
        translate the lines of a local .jazzignore file into the lines of a local .gitignore file

        :param jazzignorelines: the input lines
        :return: the .gitignore lines
        """
        recursive = False
        gitignorelines = []
        for line in jazzignorelines:
            if not line.startswith("#"):
                line = line.strip()
                if line.startswith("core.ignore"):
                    gitignorelines.append('\n')
                    if line.startswith("core.ignore.recursive"):
                        recursive = True
                    else:
                        recursive = False
                for foundpattern in Commiter.findignorepatternregex.findall(line):
                    gitignoreline = foundpattern + '\n'
                    if not recursive:
                        gitignoreline = '/' + gitignoreline    # forward, not os.sep
                    gitignorelines.append(gitignoreline)
        return gitignorelines

    @staticmethod
    def ignorejazzignore(repositoryfiles):
        """
        If a .jazzignore file is modified or added, translate it to .gitignore,
        if a .jazzignore file is deleted, delete the corresponding .gitignore file as well.

        :param repositoryfiles: the modified files
        """
        jazzignore = ".jazzignore"
        jazzignorelen = len(jazzignore)
        for repositoryfile in repositoryfiles:
            if repositoryfile[-jazzignorelen:] == jazzignore:
                path = repositoryfile[0:len(repositoryfile)-jazzignorelen]
                gitignore = path + ".gitignore"
                if os.path.exists(repositoryfile):
                    # update (or create) .gitignore
                    jazzignorelines = []
                    with open(repositoryfile, 'r') as jazzignorefile:
                        jazzignorelines = jazzignorefile.readlines()
                    if len(jazzignorelines) > 0:
                        # overwrite in any case
                        with open(gitignore, 'w') as gitignorefile:
                            gitignorefile.writelines(Commiter.translatejazzignore(jazzignorelines))
                else:
                    # delete .gitignore
                    if os.path.exists(gitignore):
                        os.remove(gitignore)


class Differ:
    @staticmethod
    def has_diff():
        return shell.execute("git diff --quiet") is 1


class ExtensionFilter:

    @staticmethod
    def match(repositoryfiles, extensions):
        """
        Determine the repository files to ignore.
        These filenames are returned as a list of newline terminated lines,
        ready to be added to .gitignore with writelines()

        :param repositoryfiles: a list of (changed) files
        :param extensions the extensions to be ignored
        :return: a list of newline terminated file names, possibly empty
        """
        repositoryfilestoignore = []
        for extension in extensions:
          for repositoryfile in repositoryfiles:
                extlen = len(extension)
                if len(repositoryfile) >= extlen:
                    if repositoryfile[-extlen:] == extension:
                        # escape a backslash with a backslash, and append a newline
                        repositoryfilestoignore.append(repositoryfile.replace('\\', '\\\\') + '\n')
        return repositoryfilestoignore
