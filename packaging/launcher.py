import multiprocessing

if __name__ == "__main__":
    # v2.1: first of all. A frozen program's worker processes (parallel extraction) are started with arguments of
    # their own, which ashare.app.main would otherwise run as a command-line command.
    multiprocessing.freeze_support()
    from ashare.app import main
    main()
